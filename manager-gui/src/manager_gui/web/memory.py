"""Research Memory catalog, detail, and policy context for the Manager GUI.

The page-local hook consumes one already-read :class:`ManagerReadModel` v0
(or reads resource ``"memory"`` through a ``ManagerDataProvider``).  The
canonical payload uses explicit ``memory_entries``, ``memory_families``,
``memory_policies``, and optional ``family_memory`` keys.  An entry may carry
``safe_summary``, ``references``, ``conflicts``, ``supersedes``, ``subject``
(``semantic_id`` and ``structural_fingerprint``), policy/bounds/source-trust/
snapshot context, and explicit inclusion/exclusion/duplicate/repeated-equivalent/
reconciliation decisions.  The parser never treats ordinary ``records`` as
memory, calls a similarity or language model, reads private storage, or exposes
mutations.  Missing source IDs remain visibly unconfirmed instead of becoming
invented URLs.

``render_memory_view(provider, ...)`` is the T3 integration hook.  T3 can mount
its returned HTML at ``data-integration-hook="memory-view"`` and pass through
its existing query string for stable catalog/detail/filter links.
"""

# HTML fragments intentionally keep readable markup even when a line is long.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from html import escape
from typing import TypeAlias, cast
from urllib.parse import parse_qsl, urlencode, urlsplit

from ..models import ManagerReadModel, ReadModelStatus, SourceReference
from ..provider import ManagerDataProvider
from .i18n import Translator, resolve_locale, with_lang
from .navigation import clear_filters_link
from .status import (
    DisplayState,
    render_operational_state,
    render_status_block,
)

QueryContext: TypeAlias = str | Mapping[str, object] | None

_MEMORY_FILTER_KEYS: tuple[str, ...] = (
    "family",
    "stage",
    "outcome",
    "failure_category",
    "campaign",
    "subject",
)
_MEMORY_CONTEXT_ORDER: tuple[str, ...] = (
    "view",
    "fixture",
    "q",
    *_MEMORY_FILTER_KEYS,
    "memory_id",
    "panel",
    "mode",
)
_MEMORY_RECORD_TYPES = frozenset(
    {
        "apex-research.memory-entry.v1",
        "apex-research.memory-policy.v1",
        "apex-research.memory-family.v1",
        "apex-research.family-memory.v1",
        "apex-research.memory-duplicate-decision.v1",
        "apex-research.memory-context.v1",
    }
)
_MEMORY_ENTRY_RECORD_TYPE = "apex-research.memory-entry.v1"
_MEMORY_POLICY_RECORD_TYPE = "apex-research.memory-policy.v1"
_MEMORY_FAMILY_RECORD_TYPE = "apex-research.memory-family.v1"
_FAMILY_MEMORY_RECORD_TYPE = "apex-research.family-memory.v1"
_MEMORY_DUPLICATE_RECORD_TYPE = "apex-research.memory-duplicate-decision.v1"
_MEMORY_CONTEXT_RECORD_TYPE = "apex-research.memory-context.v1"
MEMORY_ENTRY_RECORD_TYPE = _MEMORY_ENTRY_RECORD_TYPE
MEMORY_POLICY_RECORD_TYPE = _MEMORY_POLICY_RECORD_TYPE
MEMORY_FAMILY_RECORD_TYPE = _MEMORY_FAMILY_RECORD_TYPE
FAMILY_MEMORY_RECORD_TYPE = _FAMILY_MEMORY_RECORD_TYPE
MEMORY_DUPLICATE_DECISION_RECORD_TYPE = _MEMORY_DUPLICATE_RECORD_TYPE
MEMORY_CONTEXT_RECORD_TYPE = _MEMORY_CONTEXT_RECORD_TYPE


class MemoryAuthority(StrEnum):
    """The meaning of a Memory page's entries, not a success claim."""

    FORMAL_RESEARCH_MEMORY = "formal_research_memory"
    GUI_DERIVED = "gui_derived"


@dataclass(frozen=True, slots=True)
class MemorySubject:
    """Explicit semantic identity supplied by the Memory source."""

    semantic_id: str | None = None
    structural_fingerprint: str | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        for name in ("semantic_id", "structural_fingerprint", "label"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string or None")

    @property
    def empty(self) -> bool:
        return not any((self.semantic_id, self.structural_fingerprint, self.label))

    def to_dict(self) -> dict[str, str | None]:
        return {
            "semantic_id": self.semantic_id,
            "structural_fingerprint": self.structural_fingerprint,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class MemoryLink:
    """A source or lineage link backed only by explicit source metadata."""

    kind: str
    label: str
    target: str | None
    source_id: str | None = None
    relation: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.target)

    def __post_init__(self) -> None:
        for name in ("kind", "label"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        for name in ("target", "source_id", "relation"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string or None")

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "kind": self.kind,
            "label": self.label,
            "target": self.target,
            "source_id": self.source_id,
            "relation": self.relation,
            "available": self.available,
        }


@dataclass(frozen=True, slots=True)
class PolicyFact:
    """One explicit policy/bound/trust key-value pair."""

    key: str
    value: str

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.value.strip():
            raise ValueError("policy facts require non-empty key and value")

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "value": self.value}


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    """Snapshot identity used to qualify a Memory read."""

    token: str | None = None
    as_of: str | None = None
    revision: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"token": self.token, "as_of": self.as_of, "revision": self.revision}


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    """A read-only policy context published with Memory data."""

    policy_id: str
    policy_version: str | None = None
    bounds: tuple[PolicyFact, ...] = ()
    source_trust: tuple[PolicyFact, ...] = ()
    snapshot: MemorySnapshot = field(default_factory=MemorySnapshot)
    inclusion_rule: str | None = None
    exclusion_rule: str | None = None
    notes: str | None = None
    object_type: str = "memory-policy"

    def to_dict(self) -> dict[str, object]:
        return {
            "object_type": self.object_type,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "bounds": [fact.to_dict() for fact in self.bounds],
            "source_trust": [fact.to_dict() for fact in self.source_trust],
            "snapshot": self.snapshot.to_dict(),
            "inclusion_rule": self.inclusion_rule,
            "exclusion_rule": self.exclusion_rule,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class MemoryDecisions:
    """Explicit admission and reconciliation decisions; none are inferred."""

    inclusion: str | None = None
    exclusion: str | None = None
    duplicate: str | None = None
    repeated_equivalent: str | None = None
    reconciliation: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "inclusion": self.inclusion,
            "exclusion": self.exclusion,
            "duplicate": self.duplicate,
            "repeated_equivalent": self.repeated_equivalent,
            "reconciliation": self.reconciliation,
        }


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    """One explicitly published ``memory-entry`` ready for catalog/detail views."""

    memory_id: str
    title: str
    safe_summary: str | None = None
    family_id: str | None = None
    family_label: str | None = None
    stage: str | None = None
    outcome: str | None = None
    failure_category: str | None = None
    campaign_id: str | None = None
    subject: MemorySubject = field(default_factory=MemorySubject)
    references: tuple[MemoryLink, ...] = ()
    conflicts: tuple[MemoryLink, ...] = ()
    supersedes: tuple[MemoryLink, ...] = ()
    lineage: tuple[MemoryLink, ...] = ()
    policy: MemoryPolicy | None = None
    decisions: MemoryDecisions = field(default_factory=MemoryDecisions)
    memory_type: str = "memory-entry"
    raw: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)

    @property
    def object_type(self) -> str:
        return self.memory_type

    @property
    def has_source(self) -> bool:
        return any(link.available for link in (*self.references, *self.lineage))

    def to_dict(self) -> dict[str, object]:
        return {
            "object_type": self.memory_type,
            "memory_id": self.memory_id,
            "title": self.title,
            "safe_summary": self.safe_summary,
            "family_id": self.family_id,
            "family_label": self.family_label,
            "stage": self.stage,
            "outcome": self.outcome,
            "failure_category": self.failure_category,
            "campaign_id": self.campaign_id,
            "subject": self.subject.to_dict(),
            "references": [link.to_dict() for link in self.references],
            "conflicts": [link.to_dict() for link in self.conflicts],
            "supersedes": [link.to_dict() for link in self.supersedes],
            "lineage": [link.to_dict() for link in self.lineage],
            "policy": None if self.policy is None else self.policy.to_dict(),
            "decisions": self.decisions.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class MemoryFamily:
    """An explicit ``memory-family`` index and its ``family-memory`` members."""

    family_id: str
    label: str
    campaign_id: str | None = None
    subject: MemorySubject = field(default_factory=MemorySubject)
    entry_ids: tuple[str, ...] = ()
    references: tuple[MemoryLink, ...] = ()
    lineage: tuple[MemoryLink, ...] = ()
    policy: MemoryPolicy | None = None
    object_type: str = "memory-family"

    @property
    def memory_type(self) -> str:
        return self.object_type

    def to_dict(self) -> dict[str, object]:
        return {
            "object_type": self.object_type,
            "family_id": self.family_id,
            "label": self.label,
            "campaign_id": self.campaign_id,
            "subject": self.subject.to_dict(),
            "entry_ids": list(self.entry_ids),
            "references": [link.to_dict() for link in self.references],
            "lineage": [link.to_dict() for link in self.lineage],
            "policy": None if self.policy is None else self.policy.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class FamilyMemoryDecision:
    """One explicit inclusion/exclusion decision in a family-memory snapshot."""

    entry_id: str | None
    included: bool | None
    reason: str | None = None
    family_id: str | None = None
    source_policy_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "entry_id": self.entry_id,
            "included": self.included,
            "reason": self.reason,
            "family_id": self.family_id,
            "source_policy_id": self.source_policy_id,
        }


@dataclass(frozen=True, slots=True)
class FamilyMemory:
    """An explicit ``family-memory`` snapshot and its compatibility decisions."""

    memory_id: str
    policy_id: str | None = None
    target_family_id: str | None = None
    source_family_ids: tuple[str, ...] = ()
    snapshot_token: str | None = None
    decisions: tuple[FamilyMemoryDecision, ...] = ()
    lineage: tuple[MemoryLink, ...] = ()
    object_type: str = "family-memory"

    def to_dict(self) -> dict[str, object]:
        return {
            "object_type": self.object_type,
            "memory_id": self.memory_id,
            "policy_id": self.policy_id,
            "target_family_id": self.target_family_id,
            "source_family_ids": list(self.source_family_ids),
            "snapshot_token": self.snapshot_token,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "lineage": [link.to_dict() for link in self.lineage],
        }


@dataclass(frozen=True, slots=True)
class MemoryDuplicateDecision:
    """A canonical duplicate/repeated-equivalent/reconciliation disposition."""

    decision_id: str
    disposition: str
    subject_semantic_id: str | None = None
    structural_fingerprint: str | None = None
    matched_entry_ids: tuple[str, ...] = ()
    family_memory_id: str | None = None
    lineage: tuple[MemoryLink, ...] = ()
    object_type: str = "memory-duplicate-decision"

    def to_dict(self) -> dict[str, object]:
        return {
            "object_type": self.object_type,
            "decision_id": self.decision_id,
            "disposition": self.disposition,
            "subject_semantic_id": self.subject_semantic_id,
            "structural_fingerprint": self.structural_fingerprint,
            "matched_entry_ids": list(self.matched_entry_ids),
            "family_memory_id": self.family_memory_id,
            "lineage": [link.to_dict() for link in self.lineage],
        }


# ``family-memory`` is a published snapshot, not the ``memory-family`` index.
@dataclass(frozen=True, slots=True)
class MemoryFilters:
    """Exact, bookmarkable filters over explicit Memory dimensions."""

    family: str | None = None
    stage: str | None = None
    outcome: str | None = None
    failure_category: str | None = None
    campaign: str | None = None
    subject: str | None = None

    def __post_init__(self) -> None:
        for name in _MEMORY_FILTER_KEYS:
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string or None")

    @classmethod
    def from_query(cls, context: QueryContext) -> MemoryFilters:
        values = dict(_query_pairs(context))
        return cls(**{key: _text(values.get(key)) for key in _MEMORY_FILTER_KEYS})

    def as_query(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (key, value) for key in _MEMORY_FILTER_KEYS if (value := getattr(self, key)) is not None
        )

    def matches(self, entry: MemoryEntry) -> bool:
        values = {
            "family": (entry.family_id, entry.family_label),
            "stage": (entry.stage,),
            "outcome": (entry.outcome,),
            "failure_category": (entry.failure_category,),
            "campaign": (entry.campaign_id,),
        }
        for key, candidates in values.items():
            selected = getattr(self, key)
            if selected is not None and selected not in candidates:
                return False
        if self.subject is not None:
            subject_values = {
                entry.subject.semantic_id,
                entry.subject.structural_fingerprint,
                entry.subject.label,
            }
            if self.subject not in subject_values:
                return False
        return True


MemoryFilter = MemoryFilters


@dataclass(frozen=True, slots=True)
class MemoryViewModel:
    """Typed catalog/detail projection of an explicit ManagerReadModel Memory payload."""

    read_model: ManagerReadModel
    entries: tuple[MemoryEntry, ...]
    families: tuple[MemoryFamily, ...]
    policies: tuple[MemoryPolicy, ...]
    family_memories: tuple[FamilyMemory, ...] = ()
    duplicate_decisions: tuple[MemoryDuplicateDecision, ...] = ()
    filters: MemoryFilters = field(default_factory=MemoryFilters)
    selected_memory_id: str | None = None
    authority: MemoryAuthority = MemoryAuthority.FORMAL_RESEARCH_MEMORY
    formal_memory_present: bool = False
    explicit_memory_payload: bool = False

    @classmethod
    def from_read_model(
        cls,
        model: ManagerReadModel,
        *,
        filters: MemoryFilters | None = None,
        memory_id: str | None = None,
    ) -> MemoryViewModel:
        payload, explicit_payload = _memory_document(model.data)
        source_refs = {source.source_id: source for source in model.source_refs}
        policies = _extract_policies(payload, model)
        policy_by_id = {policy.policy_id: policy for policy in policies}
        all_entries = _extract_entries(payload, source_refs, policy_by_id, model)
        selected_filters = filters or MemoryFilters()
        entries = tuple(entry for entry in all_entries if selected_filters.matches(entry))
        families = _extract_families(payload, source_refs, policy_by_id, all_entries, model)
        family_memories = _extract_family_memories(payload, source_refs)
        duplicate_decisions = _extract_duplicate_decisions(payload, source_refs)
        authority = _authority(model, payload)
        selected = _text(memory_id)
        return cls(
            read_model=model,
            entries=entries,
            families=families,
            policies=policies,
            family_memories=family_memories,
            duplicate_decisions=duplicate_decisions,
            filters=selected_filters,
            selected_memory_id=selected,
            authority=authority,
            formal_memory_present=(
                explicit_payload and authority is MemoryAuthority.FORMAL_RESEARCH_MEMORY
            ),
            explicit_memory_payload=explicit_payload,
        )

    @classmethod
    def parse(
        cls,
        model: ManagerReadModel,
        *,
        filters: MemoryFilters | None = None,
        memory_id: str | None = None,
    ) -> MemoryViewModel:
        """Alias for integrations that call read-model parsing ``parse``."""

        return cls.from_read_model(model, filters=filters, memory_id=memory_id)

    @property
    def status(self) -> ReadModelStatus:
        return self.read_model.availability.status

    @property
    def as_of(self) -> str | None:
        return self.read_model.as_of

    @property
    def snapshot_token(self) -> str | None:
        return self.read_model.snapshot_token

    @property
    def source_refs(self) -> tuple[SourceReference, ...]:
        return self.read_model.source_refs

    @property
    def snapshot(self) -> MemorySnapshot:
        return MemorySnapshot(token=self.read_model.snapshot_token, as_of=self.read_model.as_of)

    @property
    def selected_entry(self) -> MemoryEntry | None:
        if self.selected_memory_id is None:
            return None
        return next(
            (entry for entry in self.entries if entry.memory_id == self.selected_memory_id), None
        )

    @property
    def empty(self) -> bool:
        return not self.entries

    @property
    def is_derived(self) -> bool:
        return self.authority is MemoryAuthority.GUI_DERIVED

    def to_dict(self) -> dict[str, object]:
        return {
            "authority": self.authority.value,
            "formal_memory_present": self.formal_memory_present,
            "explicit_memory_payload": self.explicit_memory_payload,
            "filters": dict(self.filters.as_query()),
            "selected_memory_id": self.selected_memory_id,
            "entries": [entry.to_dict() for entry in self.entries],
            "families": [family.to_dict() for family in self.families],
            "policies": [policy.to_dict() for policy in self.policies],
            "family_memories": [memory.to_dict() for memory in self.family_memories],
            "duplicate_decisions": [decision.to_dict() for decision in self.duplicate_decisions],
            "availability": self.read_model.availability.to_dict(),
            "snapshot": self.snapshot.to_dict(),
        }


# ------------------------------ parsing helpers -----------------------------


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return None


def _first_text(item: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = _text(item.get(key))
        if value is not None:
            return value
    return None


def _record_payloads(
    payload: Mapping[str, object], record_type: str
) -> tuple[Mapping[str, object], ...]:
    """Return payloads for the named published Memory record type only."""

    values: list[Mapping[str, object]] = []
    for raw in _sequence(payload.get("records")):
        publication = _mapping(raw)
        if publication is None or _text(publication.get("record_type")) != record_type:
            continue
        body = _mapping(publication.get("payload"))
        if body is None:
            body = publication
        merged = dict(body)
        record_id = _text(publication.get("record_id"))
        if record_id is not None:
            merged.setdefault("record_id", record_id)
        lineage = publication.get("lineage")
        if lineage is not None:
            merged.setdefault("lineage", lineage)
        values.append(cast(Mapping[str, object], merged))
    return tuple(values)


def _sequence(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return ()


def _ref_id(value: object) -> str | None:
    item = _mapping(value)
    if item is not None:
        return _first_text(item, "record_id", "source_id", "source_ref", "id", "memory_id")
    return _text(value)


def _query_pairs(context: QueryContext) -> list[tuple[str, str]]:
    if context is None:
        return []
    if isinstance(context, str):
        query = (
            urlsplit(context).query if "?" in context or "://" in context else context.lstrip("?")
        )
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
    order = {key: index for index, key in enumerate(_MEMORY_CONTEXT_ORDER)}
    values: dict[str, list[str]] = {}
    for key, value in pairs:
        if key not in values:
            values[key] = []
        if value not in values[key]:
            values[key].append(value)
    ordered = sorted(values, key=lambda key: (order.get(key, len(order)), key))
    return urlencode([(key, value) for key in ordered for value in values[key]])


def _memory_document(data: object) -> tuple[Mapping[str, object], bool]:
    """Select only an explicitly named Memory document; ordinary records are ignored."""

    root = _mapping(data)
    if root is None:
        return {}, False
    explicit_keys = {
        "memory_entries",
        "memory_entry",
        "memory_families",
        "memory_family",
        "memory_policies",
        "memory_policy",
        "family_memory",
        "memory_schema",
        "formal_research_memory",
    }
    if any(key in root for key in explicit_keys):
        return root, True
    nested = _mapping(root.get("memory"))
    if nested is not None and (
        any(key in nested for key in explicit_keys)
        or any(key in nested for key in {"entries", "families", "policies"})
        or any(_record_payloads(nested, record_type) for record_type in _MEMORY_RECORD_TYPES)
    ):
        return nested, True
    if any(_record_payloads(root, record_type) for record_type in _MEMORY_RECORD_TYPES):
        return root, True
    # An ``entries`` key is accepted only when the envelope explicitly says it is
    # a memory document.  This prevents ordinary Atlas/story records from being
    # promoted into formal memory by a convenient generic key.
    kind = _first_text(root, "memory_type", "object_type", "kind", "type")
    if kind in {"memory", "research_memory", "formal_research_memory", "gui_derived_memory"}:
        return root, True
    return {}, False


def _authority(model: ManagerReadModel, payload: Mapping[str, object]) -> MemoryAuthority:
    marker = _first_text(payload, "memory_view", "memory_authority", "memory_kind")
    if marker in {"derived", "gui_derived", "gui_derived_memory"}:
        return MemoryAuthority.GUI_DERIVED
    if model.derivation.kind in {"derived", "interpreted"} or model.availability.status in {
        ReadModelStatus.DERIVED,
        ReadModelStatus.INTERPRETED,
    }:
        return MemoryAuthority.GUI_DERIVED
    return MemoryAuthority.FORMAL_RESEARCH_MEMORY


def _pairs(value: object, *, default_key: str = "value") -> tuple[PolicyFact, ...]:
    result: list[PolicyFact] = []
    if isinstance(value, Mapping):
        for key, raw_value in value.items():
            text = _text(raw_value)
            if (
                text is None
                and isinstance(raw_value, (Mapping, Sequence))
                and not isinstance(raw_value, (str, bytes, bytearray))
            ):
                text = _compact_value(raw_value)
            if text is not None:
                result.append(PolicyFact(str(key), text))
        return tuple(result)
    for index, raw_value in enumerate(_sequence(value), start=1):
        if isinstance(raw_value, Mapping):
            item = cast(Mapping[str, object], raw_value)
            key = (
                _first_text(item, "key", "name", "field", "type", "record_type")
                or f"{default_key}-{index}"
            )
            text = _first_text(item, "value", "detail", "level", "reason", "description")
            if text is None and "rank" in item:
                text = f"{_text(item.get('rank')) or 'unknown'}"
        else:
            key = f"{default_key}-{index}"
            text = _text(raw_value)
        if text is not None:
            result.append(PolicyFact(key, text))
    return tuple(result)


def _compact_value(value: object) -> str | None:
    if isinstance(value, Mapping):
        parts = [f"{key}={_compact_value(raw) or raw!s}" for key, raw in value.items()]
        return ", ".join(parts) if parts else None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        parts = [_compact_value(raw) or str(raw) for raw in value]
        return ", ".join(parts) if parts else None
    return _text(value)


def _snapshot(item: Mapping[str, object], model: ManagerReadModel) -> MemorySnapshot:
    raw = _mapping(item.get("snapshot")) or _mapping(item.get("snapshot_context")) or {}
    return MemorySnapshot(
        token=_first_text(raw, "token", "snapshot_token")
        or _first_text(item, "snapshot_token")
        or model.snapshot_token,
        as_of=_first_text(raw, "as_of", "observed_at", "known_at")
        or _first_text(item, "as_of")
        or model.as_of,
        revision=_first_text(raw, "revision", "version"),
    )


def _policy_from_item(item: Mapping[str, object], model: ManagerReadModel) -> MemoryPolicy | None:
    raw = _mapping(item.get("policy")) or _mapping(item.get("policy_context"))
    if (
        raw is not None
        and _ref_id(raw) is not None
        and not any(
            key in raw
            for key in (
                "bounds",
                "boundaries",
                "source_trust",
                "trust",
                "allowed_record_types",
                "failure_categories",
                "duplicate_algorithm",
            )
        )
    ):
        # A PublishedRecordRef is a binding, not a complete policy document.
        raw = None
    if raw is None:
        policy_id = (
            _first_text(item, "policy_id", "memory_policy_id")
            or _ref_id(item.get("policy"))
            or _first_text(item, "record_id")
        )
        if policy_id is None:
            return None
        raw = {"policy_id": policy_id, "policy_version": _first_text(item, "policy_version")}
    policy_id = _first_text(raw, "policy_id", "record_id", "id", "name")
    if policy_id is None:
        return None
    return MemoryPolicy(
        policy_id=policy_id,
        policy_version=_first_text(raw, "policy_version", "version"),
        bounds=_pairs(raw.get("bounds", raw.get("boundaries")), default_key="bound"),
        source_trust=_pairs(raw.get("source_trust", raw.get("trust")), default_key="source"),
        snapshot=_snapshot(raw, model),
        inclusion_rule=_first_text(raw, "inclusion", "inclusion_rule", "include_rule"),
        exclusion_rule=_first_text(raw, "exclusion", "exclusion_rule", "exclude_rule"),
        notes=_first_text(raw, "notes", "note", "rationale"),
    )


def _extract_policies(
    payload: Mapping[str, object], model: ManagerReadModel
) -> tuple[MemoryPolicy, ...]:
    values: list[object] = list(_record_payloads(payload, _MEMORY_POLICY_RECORD_TYPE))
    for key in ("memory_policies", "policies"):
        values.extend(_sequence(payload.get(key)))
    for key in ("memory_policy",):
        if payload.get(key) is not None:
            values.append(payload.get(key))
    result: list[MemoryPolicy] = []
    seen: set[str] = set()
    for value in values:
        item = _mapping(value)
        if item is None:
            continue
        policy = _policy_from_item({"policy": item}, model)
        if policy is not None and policy.policy_id not in seen:
            seen.add(policy.policy_id)
            result.append(policy)
    return tuple(result)


def _subject(item: Mapping[str, object]) -> MemorySubject:
    raw = _mapping(item.get("subject")) or _mapping(item.get("subject_identity"))
    if raw is None:
        raw = item
    return MemorySubject(
        semantic_id=_first_text(raw, "semantic_id", "subject_semantic_id")
        or _first_text(item, "subject_semantic_id"),
        structural_fingerprint=_first_text(
            raw, "structural_fingerprint", "subject_structural_fingerprint"
        )
        or _first_text(item, "structural_fingerprint"),
        label=_first_text(raw, "label", "name", "title", "subject_label"),
    )


def _family_values(item: Mapping[str, object]) -> tuple[str | None, str | None]:
    raw = _mapping(item.get("family")) or _mapping(item.get("memory_family"))
    if raw is None:
        return (
            _first_text(item, "family_id", "memory_family_id"),
            _first_text(item, "family_label", "memory_family_label"),
        )
    return (
        _first_text(raw, "family_id", "record_id", "id", "semantic_id")
        or _first_text(item, "family_id", "memory_family_id"),
        _first_text(raw, "label", "title", "name", "family_key")
        or _first_text(item, "family_label", "memory_family_label", "family_key"),
    )


def _link(
    value: object,
    *,
    kind: str,
    source_refs: Mapping[str, SourceReference],
    relation: str | None = None,
) -> MemoryLink | None:
    if isinstance(value, Mapping):
        item = cast(Mapping[str, object], value)
        source_id = _first_text(item, "source_id", "source_ref", "source", "sourceId", "record_id")
        target = _first_text(item, "href", "url", "locator", "target", "uri")
        label = _first_text(item, "label", "title", "name", "id", "memory_id") or (
            source_id or kind
        )
        actual_kind = _first_text(item, "kind", "type", "source_kind") or kind
        actual_relation = _first_text(item, "relation", "decision") or relation
    else:
        source_id = _text(value)
        target = None
        label = source_id or kind
        actual_kind = kind
        actual_relation = relation
    if source_id and target is None:
        source = source_refs.get(source_id)
        if source is not None:
            target = source.locator
            actual_kind = source.kind
    return MemoryLink(
        kind=actual_kind,
        label=label,
        target=target,
        source_id=source_id,
        relation=actual_relation,
    )


def _links(
    value: object, *, kind: str, source_refs: Mapping[str, SourceReference]
) -> tuple[MemoryLink, ...]:
    result: list[MemoryLink] = []
    if isinstance(value, Mapping):
        # A mapping can be either one reference or a keyed reference collection.
        if any(
            key in value
            for key in (
                "source_id",
                "source_ref",
                "href",
                "url",
                "locator",
                "target",
                "id",
                "memory_id",
            )
        ):
            values: Sequence[object] = (value,)
        else:
            values = tuple(
                {"label": key, **(raw if isinstance(raw, Mapping) else {"target": raw})}
                for key, raw in value.items()
            )
    else:
        values = _sequence(value)
    for raw in values:
        link = _link(raw, kind=kind, source_refs=source_refs)
        if link is None:
            continue
        marker = (link.kind, link.label, link.target, link.source_id, link.relation)
        if not any(
            (existing.kind, existing.label, existing.target, existing.source_id, existing.relation)
            == marker
            for existing in result
        ):
            result.append(link)
    return tuple(result)


def _entry_from_item(
    item: Mapping[str, object],
    *,
    source_refs: Mapping[str, SourceReference],
    policy_by_id: Mapping[str, MemoryPolicy],
    model: ManagerReadModel,
    fallback_family_id: str | None = None,
    fallback_family_label: str | None = None,
) -> MemoryEntry | None:
    memory_id = _first_text(item, "memory_id", "entry_id", "id", "uid", "key")
    if memory_id is None:
        return None
    family_id, family_label = _family_values(item)
    family_id = family_id or fallback_family_id
    family_label = family_label or fallback_family_label
    inline_policy = _policy_from_item(item, model)
    policy_id = _first_text(item, "policy_id", "memory_policy_id") or _ref_id(item.get("policy"))
    policy = (policy_by_id.get(policy_id) if policy_id else None) or inline_policy
    decisions_raw = _mapping(item.get("decisions")) or _mapping(item.get("reconciliation")) or {}
    decisions = MemoryDecisions(
        inclusion=_first_text(decisions_raw, "inclusion", "include", "inclusion_decision")
        or _first_text(item, "inclusion", "inclusion_decision"),
        exclusion=_first_text(decisions_raw, "exclusion", "exclude", "exclusion_decision")
        or _first_text(item, "exclusion", "exclusion_decision"),
        duplicate=_first_text(decisions_raw, "duplicate", "duplicate_decision")
        or _first_text(item, "duplicate", "duplicate_decision"),
        repeated_equivalent=_first_text(
            decisions_raw,
            "repeated_equivalent",
            "repeated-equivalent",
            "repeated_equivalent_decision",
        )
        or _first_text(item, "repeated_equivalent", "repeated_equivalent_decision"),
        reconciliation=_first_text(decisions_raw, "reconciliation", "reconciliation_decision")
        or _first_text(item, "reconciliation_decision"),
    )
    return MemoryEntry(
        memory_id=memory_id,
        title=_first_text(item, "title", "label", "name") or memory_id,
        safe_summary=_first_text(item, "safe_summary"),
        family_id=family_id,
        family_label=family_label,
        stage=_first_text(item, "stage", "research_stage"),
        outcome=_first_text(item, "outcome", "outcome_state", "result"),
        failure_category=_first_text(item, "failure_category", "failure_class", "failure_type"),
        campaign_id=_first_text(item, "campaign_id", "campaign", "campaign_ref")
        or _ref_id(item.get("campaign")),
        subject=_subject(item),
        references=_links(
            item.get("references", item.get("source_references")),
            kind="reference",
            source_refs=source_refs,
        ),
        conflicts=_links(item.get("conflicts"), kind="conflict", source_refs=source_refs),
        supersedes=_links(
            item.get("supersedes", item.get("superseded")),
            kind="supersedes",
            source_refs=source_refs,
        ),
        lineage=_links(
            item.get("lineage", item.get("lineage_refs")), kind="lineage", source_refs=source_refs
        ),
        policy=policy,
        decisions=decisions,
        memory_type=_first_text(item, "memory_type", "object_type", "type") or "memory-entry",
        raw=item,
    )


def _entry_values(payload: Mapping[str, object]) -> list[tuple[object, str | None, str | None]]:
    result: list[tuple[object, str | None, str | None]] = [
        (value, None, None) for value in _record_payloads(payload, _MEMORY_ENTRY_RECORD_TYPE)
    ]
    for key in ("memory_entries", "entries"):
        raw = payload.get(key)
        for value in _sequence(raw):
            result.append((value, None, None))
    singular = payload.get("memory_entry")
    if singular is not None:
        result.append((singular, None, None))
    family_memory = payload.get("family_memory")
    family_values = _sequence(family_memory) if not isinstance(family_memory, Mapping) else ()
    for value in family_values:
        result.append((value, None, None))
    family_mapping = _mapping(family_memory)
    if family_mapping is not None:
        if any(
            key in family_mapping
            for key in ("entries", "memory_entries", "memory_id", "entry_id", "id")
        ):
            family_id, family_label = _family_values(family_mapping)
            for value in _sequence(
                family_mapping.get("entries", family_mapping.get("memory_entries", family_mapping))
            ):
                result.append((value, family_id, family_label))
        else:
            for family_key, raw_values in family_mapping.items():
                family_record = _mapping(raw_values)
                if family_record is not None and any(
                    key in family_record for key in ("entries", "memory_entries")
                ):
                    family_id = _first_text(family_record, "family_id", "id") or _text(family_key)
                    family_label = _first_text(family_record, "label", "title", "name")
                    values = family_record.get("entries", family_record.get("memory_entries"))
                else:
                    family_id = _text(family_key)
                    family_label = None
                    values = raw_values
                for value in _sequence(values):
                    result.append((value, family_id, family_label))
    families = _sequence(payload.get("memory_families"))
    for family in families:
        family_item = _mapping(family)
        if family_item is None:
            continue
        family_id, family_label = _family_values(family_item)
        for value in _sequence(family_item.get("entries", family_item.get("memory_entries"))):
            result.append((value, family_id, family_label))
    return result


def _extract_entries(
    payload: Mapping[str, object],
    source_refs: Mapping[str, SourceReference],
    policy_by_id: Mapping[str, MemoryPolicy],
    model: ManagerReadModel,
) -> tuple[MemoryEntry, ...]:
    result: list[MemoryEntry] = []
    seen_ids: set[str] = set()
    for raw, family_id, family_label in _entry_values(payload):
        item = _mapping(raw)
        if item is None:
            continue
        # Entries are parsed only from explicit Memory containers above.
        entry = _entry_from_item(
            item,
            source_refs=source_refs,
            policy_by_id=policy_by_id,
            model=model,
            fallback_family_id=family_id,
            fallback_family_label=family_label,
        )
        if entry is not None and entry.memory_id not in seen_ids:
            seen_ids.add(entry.memory_id)
            result.append(entry)
    return tuple(result)


def _family_from_item(
    item: Mapping[str, object],
    *,
    source_refs: Mapping[str, SourceReference],
    policy_by_id: Mapping[str, MemoryPolicy],
    entries: Sequence[MemoryEntry],
    model: ManagerReadModel,
) -> MemoryFamily | None:
    family_id, family_label = _family_values(item)
    family_id = family_id or _first_text(item, "id", "family_key")
    if family_id is None:
        return None
    linked = [entry for entry in entries if entry.family_id == family_id]
    entry_ids = _sequence(item.get("entry_ids", item.get("memory_ids")))
    explicit_ids = tuple(value for value in (_text(raw) for raw in entry_ids) if value is not None)
    return MemoryFamily(
        family_id=family_id,
        label=family_label or _first_text(item, "title", "name") or family_id,
        campaign_id=_first_text(item, "campaign_id", "campaign", "campaign_ref")
        or _ref_id(item.get("campaign")),
        subject=_subject(item),
        entry_ids=explicit_ids or tuple(entry.memory_id for entry in linked),
        references=_links(
            item.get("references", item.get("source_references")),
            kind="reference",
            source_refs=source_refs,
        ),
        lineage=_links(
            item.get("lineage", item.get("lineage_refs")), kind="lineage", source_refs=source_refs
        ),
        policy=policy_by_id.get(
            _first_text(item, "policy_id", "memory_policy_id") or _ref_id(item.get("policy")) or ""
        )
        or _policy_from_item(item, model),
    )


def _extract_families(
    payload: Mapping[str, object],
    source_refs: Mapping[str, SourceReference],
    policy_by_id: Mapping[str, MemoryPolicy],
    entries: Sequence[MemoryEntry],
    model: ManagerReadModel,
) -> tuple[MemoryFamily, ...]:
    result: list[MemoryFamily] = []
    seen: set[str] = set()
    raw_values: list[object] = list(_record_payloads(payload, _MEMORY_FAMILY_RECORD_TYPE))
    raw_values.extend(_sequence(payload.get("memory_families")))
    singular = payload.get("memory_family")
    if singular is not None:
        raw_values.append(singular)
    family_memory = _mapping(payload.get("family_memory"))
    if family_memory is not None and not any(
        key in family_memory for key in ("entries", "memory_entries", "memory_id", "entry_id", "id")
    ):
        for family_key, raw in family_memory.items():
            item = _mapping(raw)
            if item is None:
                item = {"family_id": family_key, "entries": raw}
            elif _family_values(item)[0] is None:
                item = {**item, "family_id": family_key}
            raw_values.append(item)
    for raw in raw_values:
        item = _mapping(raw)
        if item is None:
            continue
        family = _family_from_item(
            item,
            source_refs=source_refs,
            policy_by_id=policy_by_id,
            entries=entries,
            model=model,
        )
        if family is not None and family.family_id not in seen:
            seen.add(family.family_id)
            result.append(family)
    # An explicit family_id on an entry is enough to expose its family index; it
    # is not a conversion of an ordinary record because entries came from a named
    # Memory container above.
    for entry in entries:
        if entry.family_id and entry.family_id not in seen:
            seen.add(entry.family_id)
            result.append(
                MemoryFamily(
                    family_id=entry.family_id,
                    label=entry.family_label or entry.family_id,
                    campaign_id=entry.campaign_id,
                    subject=entry.subject,
                    entry_ids=tuple(
                        item.memory_id for item in entries if item.family_id == entry.family_id
                    ),
                    policy=entry.policy,
                )
            )
    return tuple(result)


def _family_memory_values(payload: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    values: list[Mapping[str, object]] = list(_record_payloads(payload, _FAMILY_MEMORY_RECORD_TYPE))
    raw = payload.get("family_memory")
    if isinstance(raw, Mapping) and any(
        key in raw
        for key in ("policy", "target_family", "source_families", "decisions", "snapshot_token")
    ):
        values.append(cast(Mapping[str, object], raw))
    for value in _sequence(raw):
        item = _mapping(value)
        if item is not None:
            values.append(item)
    return tuple(values)


def _family_memory_from_item(
    item: Mapping[str, object],
    source_refs: Mapping[str, SourceReference],
) -> FamilyMemory | None:
    memory_id = _first_text(item, "memory_id", "content_id", "record_id", "id")
    if memory_id is None:
        return None
    policy_id = _ref_id(item.get("policy")) or _first_text(item, "policy_id")
    target_family_id = _ref_id(item.get("target_family")) or _first_text(item, "target_family_id")
    source_family_ids = tuple(
        value
        for value in (_ref_id(raw) for raw in _sequence(item.get("source_families")))
        if value is not None
    )
    decision_values: list[object] = []
    raw_decisions = item.get("decisions")
    if isinstance(raw_decisions, Mapping) and any(
        key in raw_decisions for key in ("included", "excluded")
    ):
        for raw in _sequence(raw_decisions.get("included")):
            decision_values.append(
                {"included": True, **(raw if isinstance(raw, Mapping) else {"entry_id": raw})}
            )
        for raw in _sequence(raw_decisions.get("excluded")):
            decision_values.append(
                {"included": False, **(raw if isinstance(raw, Mapping) else {"entry_id": raw})}
            )
    else:
        decision_values.extend(_sequence(raw_decisions))
    decisions: list[FamilyMemoryDecision] = []
    for raw in decision_values:
        decision = _mapping(raw)
        if decision is None:
            continue
        fact = decision.get("fact", decision.get("reference", decision.get("entry")))
        entry_id = _ref_id(fact) or _first_text(decision, "entry_id", "memory_id", "record_id")
        included = decision.get("included")
        if not isinstance(included, bool):
            included = None
        decisions.append(
            FamilyMemoryDecision(
                entry_id=entry_id,
                included=included,
                reason=_first_text(decision, "reason", "exclusion_reason", "disposition"),
                family_id=_ref_id(decision.get("family")) or _first_text(decision, "family_id"),
                source_policy_id=_ref_id(decision.get("source_policy"))
                or _first_text(decision, "source_policy_id"),
            )
        )
    return FamilyMemory(
        memory_id=memory_id,
        policy_id=policy_id,
        target_family_id=target_family_id,
        source_family_ids=source_family_ids,
        snapshot_token=_first_text(item, "snapshot_token"),
        decisions=tuple(decisions),
        lineage=_links(item.get("lineage"), kind="lineage", source_refs=source_refs),
    )


def _extract_family_memories(
    payload: Mapping[str, object], source_refs: Mapping[str, SourceReference]
) -> tuple[FamilyMemory, ...]:
    result: list[FamilyMemory] = []
    seen: set[str] = set()
    for item in _family_memory_values(payload):
        memory = _family_memory_from_item(item, source_refs)
        if memory is not None and memory.memory_id not in seen:
            seen.add(memory.memory_id)
            result.append(memory)
    return tuple(result)


def _duplicate_values(payload: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    values = list(_record_payloads(payload, _MEMORY_DUPLICATE_RECORD_TYPE))
    for key in ("memory_duplicate_decisions", "duplicate_decisions"):
        values.extend(
            item
            for item in (_mapping(raw) for raw in _sequence(payload.get(key)))
            if item is not None
        )
    return tuple(values)


def _extract_duplicate_decisions(
    payload: Mapping[str, object], source_refs: Mapping[str, SourceReference]
) -> tuple[MemoryDuplicateDecision, ...]:
    result: list[MemoryDuplicateDecision] = []
    seen: set[str] = set()
    for item in _duplicate_values(payload):
        decision_id = _first_text(item, "decision_id", "record_id", "id")
        if decision_id is None:
            continue
        matched = tuple(
            value
            for value in (_ref_id(raw) for raw in _sequence(item.get("matched")))
            if value is not None
        )
        decision = MemoryDuplicateDecision(
            decision_id=decision_id,
            disposition=_first_text(item, "disposition", "decision", "outcome") or "unknown",
            subject_semantic_id=_first_text(item, "subject_semantic_id", "semantic_id"),
            structural_fingerprint=_first_text(item, "structural_fingerprint"),
            matched_entry_ids=matched,
            family_memory_id=_first_text(item, "family_memory_id"),
            lineage=_links(item.get("lineage"), kind="lineage", source_refs=source_refs),
        )
        if decision.decision_id not in seen:
            seen.add(decision.decision_id)
            result.append(decision)
    return tuple(result)


# ------------------------------- links/render -------------------------------


def memory_link(
    memory_id: str | None = None,
    *,
    query_context: QueryContext = None,
    filters: MemoryFilters | None = None,
    base_path: str = "/",
) -> str:
    """Build a stable catalog/detail URL without manufacturing source links."""

    if memory_id is not None and (not isinstance(memory_id, str) or not memory_id.strip()):
        raise ValueError("memory_id must be a non-empty string or None")
    pairs = _query_pairs(query_context)
    if filters is not None:
        pairs = [
            (key, value)
            for key, value in pairs
            if key not in {"view", "memory_id", *_MEMORY_FILTER_KEYS}
        ]
    else:
        pairs = [(key, value) for key, value in pairs if key not in {"view", "memory_id"}]
    pairs.append(("view", "memory"))
    if filters is not None:
        pairs.extend(filters.as_query())
    if memory_id is not None:
        pairs.append(("memory_id", memory_id))
    query = _stable_query(pairs)
    if not query:
        return base_path
    separator = "&" if "?" in base_path else "?"
    return f"{base_path}{separator}{query}"


build_memory_link = memory_link


def _context_with_filters(view: MemoryViewModel, context: QueryContext) -> QueryContext:
    pairs = _query_pairs(context)
    present = {key for key, _ in pairs}
    pairs.extend((key, value) for key, value in view.filters.as_query() if key not in present)
    return "?" + _stable_query(pairs) if pairs else None


_S3_FIXTURE_COPY = {
    "Formal data-gate failure memory": "memory_title",
    "The declared data gate rejected the candidate.": "memory_summary",
    "Fixture data quality": "family_label",
    "Fixture candidate": "subject_label",
    "admitted by the owner-published policy": "inclusion_rule",
    "outside the declared fixture scope": "exclusion_rule",
    "Fixture data gate failure": "failure_title",
    "The adapter did not expose the required data field.": "failure_summary",
    "All fixture lineage dimensions are explicitly published.": "lineage_reason",
    "Repeated fixture data-gate failures": "pattern_title",
    "group by failure_category and stage": "pattern_rule",
    "Partial fixture failure memory": "partial_title",
    "Only the campaign-side failure record is in scope.": "partial_summary",
}


def render_memory_text(value: str | None, translator: Translator, model: ManagerReadModel | None = None, *, missing: str = "l4.missing_unconfirmed") -> str:
    """Localize only the known synthetic fixture; all other text is owner-owned."""
    if value is None:
        return translator.html(missing)
    fixture = model is not None and bool(model.source_refs) and all(
        source.schema == "s3.fixture.v0" for source in model.source_refs
    ) and (model.snapshot_token or "").startswith("fixture-s3-")
    if fixture and value in _S3_FIXTURE_COPY:
        return translator.html("l4.fixture." + _S3_FIXTURE_COPY[value])
    return f'<span data-owner-text="true">{translator.source_text(value)}</span>'


def render_memory_value(value: str | None, translator: Translator, domain: str | None = None, *, missing: str = "l4.missing_unconfirmed") -> str:
    """Keep identities opaque and open values verbatim, while mapping known enums."""
    if value is None:
        return translator.html(missing)
    if domain is None:
        return f'<span translate="no">{translator.source_text(value)}</span>'
    known_aliases = {"not excluded": "not_excluded", "not repeated": "not_repeated", "not required": "not_required"}
    label = translator.label(domain, known_aliases.get(value, value) if domain == "decision" else value)
    return label.replace("<code>", '<code translate="no">', 1) if label.startswith("<code>") else label


def render_filter_value(value: str, translator: Translator, domain: str | None = None) -> str:
    if domain is None:
        return translator.source_text(value)
    label = translator.label(domain, value)
    return translator.source_text(value) if label.startswith("<code>") else label


def memory_source_link(target: str, context: QueryContext) -> str:
    """Propagate only language to published local targets, never foreign read pins."""
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not parts.path.startswith("/"):
        return target
    raw_lang = next((value for key, value in _query_pairs(context) if key == "lang"), None)
    return with_lang(target, resolve_locale(raw_lang))


def _render_links(links: Sequence[MemoryLink], *, translator: Translator, context: QueryContext = None) -> str:
    if not links:
        return f'<span class="memory-source-missing">{translator.html("l4.missing_source")}</span>'
    rendered: list[str] = []
    for link in links:
        label = f'{render_memory_text(link.label, translator)} [{render_memory_value(link.kind, translator, "memory_link_kind")}]'
        relation = f' data-link-relation="{escape(link.relation, quote=True)}"' if link.relation else ""
        attrs = f'data-link-kind="{escape(link.kind, quote=True)}"{relation}'
        if link.target:
            target = memory_source_link(link.target, context)
            rendered.append(f'<a class="memory-link memory-{escape(link.kind, quote=True)}" {attrs} href="{escape(target, quote=True)}">{label}</a>')
        else:
            rendered.append(f'<span class="memory-link-unconfirmed" {attrs}>{label} · {translator.html("l4.missing_source")}</span>')
    return '<span class="memory-links">' + " · ".join(rendered) + "</span>"


def _render_facts(title_key: str, facts: Sequence[PolicyFact], *, section_id: str, translator: Translator) -> str:
    if not facts:
        return f'<div class="memory-facts-empty" data-facts="{escape(section_id)}">{translator.html("l4.none_recorded")}</div>'
    rows = "".join(
        f'<div class="memory-fact"><dt>{render_memory_value(fact.key, translator, "policy_field")}</dt><dd>{render_memory_value(fact.value, translator)}</dd></div>'
        for fact in facts
    )
    return f'<section class="memory-context-section" id="{escape(section_id, quote=True)}"><h3>{translator.html(title_key)}</h3><dl>{rows}</dl></section>'


def _render_policy(policy: MemoryPolicy | None, *, translator: Translator, model: ManagerReadModel, heading: str = "l4.policy_context") -> str:
    if policy is None:
        return f'<section class="memory-policy" data-memory-object="memory-policy"><h2>{translator.html(heading)}</h2><p>{translator.html("l4.policy_unavailable")}</p></section>'
    snapshot = policy.snapshot
    snapshot_text = " · ".join(
        part for part in (
            f'{translator.html("l4.token")} {render_memory_value(snapshot.token, translator, missing="l4.unavailable")}',
            f'{translator.html("l4.as_of")} {render_memory_value(snapshot.as_of, translator, missing="l4.unavailable")}',
            f'{translator.html("l4.revision")} {render_memory_value(snapshot.revision, translator)}' if snapshot.revision else None,
        ) if part
    )
    rules = "".join(
        f'<div class="memory-fact"><dt>{translator.html(key)}</dt><dd>{render_memory_text(value, translator, model, missing="l4.none_recorded")}</dd></div>'
        for key, value in (("l4.inclusion_rule", policy.inclusion_rule), ("l4.exclusion_rule", policy.exclusion_rule))
    )
    notes = f'<p class="memory-policy-notes">{render_memory_text(policy.notes, translator, model)}</p>' if policy.notes else ""
    version = f' · {translator.html("l4.version")} {render_memory_value(policy.policy_version, translator)}' if policy.policy_version else ""
    return (
        f'<section class="memory-policy" data-memory-object="memory-policy"><h2>{translator.html(heading)}</h2>'
        f'<p class="memory-policy-id"><strong>{translator.html("l4.policy")}</strong> {render_memory_value(policy.policy_id, translator)}{version}</p>'
        f'<p class="memory-snapshot"><strong>{translator.html("l4.snapshot")}</strong> {snapshot_text}</p>'
        f'<dl class="memory-policy-rules">{rules}</dl>'
        f'{_render_facts("l4.bounds", policy.bounds, section_id="memory-bounds", translator=translator)}'
        f'{_render_facts("l4.source_trust", policy.source_trust, section_id="memory-source-trust", translator=translator)}'
        f'{notes}</section>'
    )


def _render_decisions(decisions: MemoryDecisions, *, translator: Translator) -> str:
    rows = "".join(
        f'<div class="memory-decision"><dt>{translator.html(key)}</dt><dd>{render_memory_value(value, translator, "decision", missing="l4.none_recorded")}</dd></div>'
        for key, value in (
            ("l4.inclusion_decision", decisions.inclusion),
            ("l4.exclusion_decision", decisions.exclusion),
            ("l4.duplicate_decision", decisions.duplicate),
            ("l4.repeated_equivalent_decision", decisions.repeated_equivalent),
            ("l4.reconciliation_decision", decisions.reconciliation),
        )
    )
    return f'<section class="memory-decisions"><h3>{translator.html("l4.memory_decisions")}</h3><dl>{rows}</dl></section>'


def _render_subject(subject: MemorySubject, *, translator: Translator, model: ManagerReadModel) -> str:
    rows = "".join(
        f'<div class="memory-subject-fact"><dt>{translator.html(key)}</dt><dd>{value}</dd></div>'
        for key, value in (
            ("l4.subject_semantic_id", render_memory_value(subject.semantic_id, translator)),
            ("l4.structural_fingerprint", render_memory_value(subject.structural_fingerprint, translator)),
            ("l4.subject_label", render_memory_text(subject.label, translator, model)),
        )
    )
    return f'<section class="memory-subject"><h3>{translator.html("l4.subject_identity")}</h3><dl>{rows}</dl></section>'


def _render_entry_cross_layer_links(entry: MemoryEntry, *, context: QueryContext, translator: Translator) -> str:
    """Expose only owner-published failure/pattern identities on the Memory path."""

    failure_id = _first_text(entry.raw, "failure_id", "failure_ref")
    pattern_id = _first_text(entry.raw, "pattern_id", "pattern_ref")
    links: list[str] = []
    if failure_id or pattern_id:
        # Local import avoids a module cycle: failure_patterns consumes Memory's parser.
        from .failure_patterns import failure_link

    if failure_id:
        links.append(
            f'<a class="memory-failure-link" href="{escape(failure_link(failure_id, query_context=context, view="memory-failures"), quote=True)}">{translator.html("l4.open_memory_failure")}</a>'
        )
    if pattern_id:
        links.append(
            f'<a class="memory-pattern-link" href="{escape(failure_link(pattern_id=pattern_id, query_context=context), quote=True)}">{translator.html("l4.failure_patterns_open")}</a>'
        )
    return f'<p class="memory-cross-layer-links">{" · ".join(links)}</p>' if links else ""


def _render_entry_detail(entry: MemoryEntry, *, context: QueryContext, translator: Translator, model: ManagerReadModel) -> str:
    relation_sections = "".join(
        f'<section class="memory-relation" data-relation="{relation}"><h3>{translator.html(key)}</h3>{_render_links(getattr(entry, relation), translator=translator, context=context)}</section>'
        for relation, key in (("references", "l4.references"), ("conflicts", "l4.conflicts"), ("supersedes", "l4.supersedes"), ("lineage", "l4.lineage"))
    )
    family = render_memory_text(entry.family_label, translator, model) if entry.family_label else render_memory_value(entry.family_id, translator)
    return (
        f'<article class="memory-detail" data-memory-object="memory-entry" data-memory-entry-id="{escape(entry.memory_id, quote=True)}">'
        f'<p class="eyebrow">{translator.html("l4.memory_entry_eyebrow")}</p>'
        f'<h2>{render_memory_text(entry.title, translator, model)}</h2>'
        f'<p class="memory-detail-id"><strong>{translator.html("l4.memory_id")}</strong> {render_memory_value(entry.memory_id, translator)} · <strong>{translator.html("l4.family")}</strong> {family}</p>'
        f'<p class="memory-safe-summary"><strong>{translator.html("l4.safe_summary")}</strong> {render_memory_text(entry.safe_summary, translator, model, missing="l4.no_safe_summary")}</p>'
        f'<dl class="memory-entry-facts"><div><dt>{translator.html("l4.stage")}</dt><dd>{render_memory_value(entry.stage, translator, "failure_stage")}</dd></div>'
        f'<div><dt>{translator.html("l4.outcome")}</dt><dd>{render_memory_value(entry.outcome, translator, "failure_outcome")}</dd></div>'
        f'<div><dt>{translator.html("l4.failure_category")}</dt><dd>{render_memory_value(entry.failure_category, translator, "failure_category")}</dd></div>'
        f'<div><dt>{translator.html("l4.campaign")}</dt><dd>{render_memory_value(entry.campaign_id, translator)}</dd></div></dl>'
        f'{_render_subject(entry.subject, translator=translator, model=model)}{relation_sections}'
        f'{_render_entry_cross_layer_links(entry, context=context, translator=translator)}'
        f'{_render_decisions(entry.decisions, translator=translator)}'
        f'{_render_policy(entry.policy, translator=translator, model=model)}'
        f'<p><a class="memory-back-link" href="{escape(memory_link(query_context=context), quote=True)}">{translator.html("l4.back_memory_catalog")}</a></p></article>'
    )


def _render_entry_row(entry: MemoryEntry, *, context: QueryContext, translator: Translator, model: ManagerReadModel) -> str:
    family = render_memory_text(entry.family_label, translator, model) if entry.family_label else render_memory_value(entry.family_id, translator)
    source = _render_links(entry.references, translator=translator, context=context)
    return (
        f'<tr class="memory-entry-row" data-memory-entry-id="{escape(entry.memory_id, quote=True)}" data-family="{escape(entry.family_id or "", quote=True)}">'
        f'<th scope="row"><a class="memory-entry-link" href="{escape(memory_link(entry.memory_id, query_context=context), quote=True)}">{render_memory_text(entry.title, translator, model)}</a><br><small translate="no">{translator.source_text(entry.memory_id)}</small></th>'
        f'<td>{family}</td><td>{render_memory_value(entry.stage, translator, "failure_stage")}</td>'
        f'<td>{render_memory_value(entry.outcome, translator, "failure_outcome")}</td><td>{render_memory_value(entry.failure_category, translator, "failure_category")}</td>'
        f'<td>{render_memory_value(entry.subject.semantic_id, translator)}</td><td>{source}</td></tr>'
    )


def _render_filters(view: MemoryViewModel, *, context: QueryContext, translator: Translator) -> str:
    values = {key: getattr(view.filters, key) or "" for key in _MEMORY_FILTER_KEYS}
    context_pairs = [
        (key, value)
        for key, value in _query_pairs(context)
        if key not in {"view", "memory_id", *_MEMORY_FILTER_KEYS}
    ]
    hidden = "".join(
        f'<input type="hidden" name="{escape(key, quote=True)}" value="{escape(value, quote=True)}">'
        for key, value in context_pairs
    )
    options: dict[str, tuple[str, ...]] = {}
    for key in _MEMORY_FILTER_KEYS:
        options[key] = tuple(
            sorted(
                {
                    value
                    for entry in view.entries
                    for value in (
                        (
                            entry.family_id
                            if key == "family"
                            else entry.stage
                            if key == "stage"
                            else entry.outcome
                            if key == "outcome"
                            else entry.failure_category
                            if key == "failure_category"
                            else entry.campaign_id
                            if key == "campaign"
                            else entry.subject.semantic_id
                            if key == "subject"
                            else None
                        ),
                    )
                    if value is not None
                }
            )
        )
    controls: list[str] = []
    domains = {"stage": "failure_stage", "outcome": "failure_outcome", "failure_category": "failure_category"}
    for key in _MEMORY_FILTER_KEYS:
        choices = "".join(
            f'<option value="{escape(choice, quote=True)}"{(" selected" if values[key] == choice else "")} translate="no">{render_filter_value(choice, translator, domains.get(key))}</option>'
            for choice in options[key]
        )
        controls.append(
            f'<label>{translator.html("l4." + key)} <select name="{escape(key, quote=True)}"><option value="">{translator.html("l4.all")}</option>{choices}</select></label>'
        )
    clear_href = clear_filters_link(
        context, view="memory", filter_keys=_MEMORY_FILTER_KEYS, selection_keys=("memory_id",)
    )
    return (
        f'<form class="memory-filters" action="/" method="get" aria-label="{escape(translator.t("l4.memory_filters_aria"), quote=True)}">'
        '<input type="hidden" name="view" value="memory">'
        f"{hidden}{''.join(controls)}"
        f'<button type="submit">{translator.html("l4.apply_filters")}</button><a class="memory-clear" href="{escape(clear_href, quote=True)}">{translator.html("l4.clear")}</a></form>'
    )


def _render_family_memories(view: MemoryViewModel, *, translator: Translator, context: QueryContext) -> str:
    if not view.family_memories:
        return ""
    sections: list[str] = []
    for memory in view.family_memories:
        decisions = "".join(
            f'<li data-entry-id="{escape(decision.entry_id or "", quote=True)}">'
            f'<strong>{translator.html("l4.included" if decision.included is True else "l4.excluded" if decision.included is False else "l4.undetermined")}</strong> '
            f'{render_memory_value(decision.entry_id, translator)}'
            f'{" · " + render_memory_text(decision.reason, translator, view.read_model) if decision.reason else ""}</li>'
            for decision in memory.decisions
        ) or f'<li>{translator.html("l4.none_recorded")}</li>'
        sections.append(
            f'<article class="family-memory" data-memory-object="family-memory" data-family-memory-id="{escape(memory.memory_id, quote=True)}">'
            f'<h3>{translator.html("l4.family_memory")} {render_memory_value(memory.memory_id, translator)}</h3>'
            f'<p><strong>{translator.html("l4.target_family")}</strong> {render_memory_value(memory.target_family_id, translator)} · '
            f'<strong>{translator.html("l4.policy")}</strong> {render_memory_value(memory.policy_id, translator)} · '
            f'<strong>{translator.html("l4.snapshot")}</strong> {render_memory_value(memory.snapshot_token, translator, missing="l4.unavailable")}</p>'
            f'<h4>{translator.html("l4.inclusion_exclusion_decisions")}</h4><ul>{decisions}</ul>'
            f'<p>{_render_links(memory.lineage, translator=translator, context=context)}</p></article>'
        )
    return f'<section class="memory-family-memory"><h2>{translator.html("l4.family_memories")}</h2>{"".join(sections)}</section>'


def _render_duplicate_decisions(view: MemoryViewModel, *, translator: Translator, context: QueryContext) -> str:
    if not view.duplicate_decisions:
        return ""
    rows = "".join(
        f'<li data-decision-id="{escape(decision.decision_id, quote=True)}"><strong>{render_memory_value(decision.disposition, translator, "decision")}</strong> '
        f'{render_memory_value(decision.decision_id, translator)} · {translator.count("l4.matched_count", len(decision.matched_entry_ids))}'
        f'{(" · " + render_memory_value(decision.subject_semantic_id, translator)) if decision.subject_semantic_id else ""}'
        f'{(" · " + render_memory_value(decision.structural_fingerprint, translator)) if decision.structural_fingerprint else ""}'
        f' {_render_links(decision.lineage, translator=translator, context=context)}</li>'
        for decision in view.duplicate_decisions
    )
    return f'<section class="memory-duplicate-decisions"><h2>{translator.html("l4.duplicate_decisions")}</h2><ul>{rows}</ul></section>'


def _render_families(view: MemoryViewModel, *, context: QueryContext, translator: Translator) -> str:
    if not view.families:
        return f'<section class="memory-families" data-memory-object="memory-family"><h2>{translator.html("l4.memory_families")}</h2><p>{translator.html("l4.none_recorded")}</p></section>'
    items = "".join(
        f'<li data-family-id="{escape(family.family_id, quote=True)}"><strong>{render_memory_text(family.label, translator, view.read_model)}</strong> '
        f'<span>{render_memory_value(family.family_id, translator)} · {translator.count("l4.entries_count", len(family.entry_ids))}</span>'
        f'{("<span> · " + translator.html("l4.campaign") + " " + render_memory_value(family.campaign_id, translator) + "</span>") if family.campaign_id else ""}'
        f'<a href="{escape(memory_link(query_context=context, filters=MemoryFilters(family=family.family_id)), quote=True)}">{translator.html("l4.open_family_memory")}</a>'
        f'{_render_links(family.lineage, translator=translator, context=context)}</li>'
        for family in view.families
    )
    return f'<section class="memory-families" data-memory-object="memory-family"><h2>{translator.html("l4.memory_families")} / {translator.html("l4.family_memory")}</h2><ul>{items}</ul></section>'


def _render_policy_index(view: MemoryViewModel, *, translator: Translator) -> str:
    if not view.policies:
        return f'<section class="memory-policy-index"><h2>{translator.html("l4.memory_policies")}</h2><p>{translator.html("l4.none_recorded")}</p></section>'
    items: list[str] = []
    for policy in view.policies:
        version = f' · {translator.html("l4.version")} {render_memory_value(policy.policy_version, translator)}' if policy.policy_version else ""
        items.append(
            f'<li data-policy-id="{escape(policy.policy_id, quote=True)}"><strong>{render_memory_value(policy.policy_id, translator)}</strong>{version}'
            f' · {translator.count("l4.bounds_count", len(policy.bounds))} · {translator.count("l4.trust_count", len(policy.source_trust))}</li>'
        )
    return f'<section class="memory-policy-index"><h2>{translator.html("l4.memory_policies")}</h2><ul>{"".join(items)}</ul></section>'


def _render_derivation(model: ManagerReadModel, *, sample_count: int, translator: Translator) -> str:
    derivation = model.derivation
    if derivation.kind == "direct":
        return ""
    inputs = translator.join(render_memory_value(value, translator) for value in derivation.inputs) if derivation.inputs else translator.html("l4.none_recorded")
    return (
        f'<section class="memory-derived-context" data-memory-derived="true"><h2>{translator.html("l4.derivation_context")}</h2>'
        f'<dl><div><dt>{translator.html("l4.derivation_kind")}</dt><dd>{render_memory_value(derivation.kind, translator, "derivation_kind")}</dd></div>'
        f'<div><dt>{translator.html("l4.rule")}</dt><dd>{render_memory_value(derivation.rule, translator)}</dd></div>'
        f'<div><dt>{translator.html("l4.named_inputs")}</dt><dd>{inputs}</dd></div>'
        f'<div><dt>{translator.html("l4.version")}</dt><dd>{render_memory_value(derivation.version, translator)}</dd></div>'
        f'<div><dt>{translator.html("l4.sample_count")}</dt><dd>{sample_count}</dd></div></dl>'
        f'<p>{translator.html("l4.derived_not_formal_memory")}</p></section>'
    )


def render_memory(
    view_or_model: MemoryViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    memory_id: str | None = None,
    translator: Translator | None = None,
) -> str:
    """Render a Memory catalog/detail fragment; the shared shell owns document chrome."""

    translator = translator or Translator()
    if isinstance(view_or_model, MemoryViewModel):
        view = view_or_model
    else:
        view = MemoryViewModel.from_read_model(
            view_or_model,
            filters=MemoryFilters.from_query(query_context),
            memory_id=memory_id or dict(_query_pairs(query_context)).get("memory_id"),
        )
    context = _context_with_filters(view, query_context)
    model = view.read_model
    sources = translator.join(render_memory_value(source.source_id, translator) for source in model.source_refs) or translator.html("l4.none_recorded")
    authority_copy = translator.html("l4.memory_derived_authority" if view.is_derived else "l4.memory_formal_authority")
    pieces = [
        '<section class="research-memory" data-integration-hook="memory-view" '
        f'data-memory-authority="{view.authority.value}" data-memory-empty="{"true" if view.empty else "false"}">',
        f'<p class="eyebrow">{translator.html("l4.memory_eyebrow")}</p>',
        f'<h1 class="page-title" data-page-title tabindex="-1">{translator.html("l4.memory_title")}</h1>',
        f'<p class="memory-authority" data-memory-authority-label="{view.authority.value}"><strong>{translator.label("memory_authority", view.authority.value)}</strong> {authority_copy}</p>',
        f'<p class="context-line memory-context"><span><strong>{translator.html("l4.observed")}</strong> {render_memory_value(model.as_of, translator, missing="l4.unavailable")}</span>'
        f'<span><strong>{translator.html("l4.snapshot")}</strong> {render_memory_value(model.snapshot_token, translator, missing="l4.unavailable")}</span><span><strong>{translator.html("l4.sources")}</strong> {sources}</span></p>',
        render_status_block(model, translator=translator),
    ]
    if view.is_derived:
        pieces.append(_render_derivation(model, sample_count=len(view.entries), translator=translator))
    if view.empty:
        detail = translator.html("l4.no_formal_memory" if not view.explicit_memory_payload else "l4.no_formal_memory_scope")
        if model.availability.status in {ReadModelStatus.MISSING, ReadModelStatus.KNOWN}:
            pieces.append(render_operational_state(DisplayState.EMPTY, translator=translator))
            pieces.append(f'<p class="memory-empty-detail">{detail}</p>')
        else:
            status = translator.t("label.status." + model.availability.status.value)
            pieces.append(
                f'<p class="memory-empty-not-determined" data-memory-empty-state="not-determined">'
                f'{translator.html("l4.memory_not_determined", status=status)}</p>'
            )
    if model.availability.status is ReadModelStatus.KNOWN and not model.availability.complete:
        pieces.append(
            f'<p class="memory-partial-note">{translator.html("l4.partial_memory_scope")}</p>'
        )
    pieces.append(_render_filters(view, context=context, translator=translator))
    selected = view.selected_entry
    if view.selected_memory_id is not None and selected is None:
        pieces.append(
            f'<section class="memory-detail-missing" data-memory-detail="missing"><h2>{translator.html("l4.memory_detail_unavailable")}</h2>'
            f'<p>{render_memory_value(view.selected_memory_id, translator)} · {translator.html("l4.failure_snapshot_missing")}</p></section>'
        )
    elif selected is not None:
        pieces.append(_render_entry_detail(selected, context=context, translator=translator, model=model))
    if view.entries:
        rows = "".join(_render_entry_row(entry, context=context, translator=translator, model=model) for entry in view.entries)
        pieces.append(
            f'<section class="memory-catalog" data-memory-object="memory-entry"><h2>{translator.html("l4.memory_entry_catalog")}</h2>'
            f'<table><caption>{translator.html("l4.explicit_memory_entries")}</caption><thead><tr>'
            f'<th scope="col">{translator.html("l4.memory_entry")}</th><th scope="col">{translator.html("l4.family")}</th><th scope="col">{translator.html("l4.stage")}</th>'
            f'<th scope="col">{translator.html("l4.outcome")}</th><th scope="col">{translator.html("l4.failure_category")}</th><th scope="col">{translator.html("l4.subject_semantic_id")}</th><th scope="col">{translator.html("l4.references")}</th>'
            f"</tr></thead><tbody>{rows}</tbody></table></section>"
        )
    pieces.append(_render_families(view, context=context, translator=translator))
    pieces.append(_render_family_memories(view, translator=translator, context=context))
    pieces.append(_render_duplicate_decisions(view, translator=translator, context=context))
    pieces.append(_render_policy_index(view, translator=translator))
    policy = (
        selected.policy if selected is not None else (view.policies[0] if view.policies else None)
    )
    pieces.append(_render_policy(policy, heading="l4.active_policy_context", translator=translator, model=model))
    pieces.append("</section>")
    return "".join(pieces)


def memory_view(
    provider: ManagerDataProvider,
    *,
    filters: MemoryFilters | None = None,
    query_context: QueryContext = None,
    memory_id: str | None = None,
    snapshot_token: str | None = None,
) -> MemoryViewModel:
    """Read the named ``memory`` resource through the public provider seam."""

    selected_filters = filters or MemoryFilters.from_query(query_context)
    selected_id = memory_id or dict(_query_pairs(query_context)).get("memory_id")
    # The provider is the only read boundary; the parser performs no additional I/O.
    model = provider.read("memory", snapshot_token=snapshot_token)
    return MemoryViewModel.from_read_model(model, filters=selected_filters, memory_id=selected_id)


def render_memory_view(
    provider: ManagerDataProvider,
    *,
    filters: MemoryFilters | None = None,
    query_context: QueryContext = None,
    memory_id: str | None = None,
    snapshot_token: str | None = None,
    translator: Translator | None = None,
) -> str:
    """T3 integration hook: read and render Memory without shell logic."""

    return render_memory(
        memory_view(
            provider,
            filters=filters,
            query_context=query_context,
            memory_id=memory_id,
            snapshot_token=snapshot_token,
        ),
        query_context=query_context,
        translator=translator,
    )


MEMORY_INTEGRATION_HOOK = "manager_gui.web.memory.render_memory_view"
render_memory_view_model = memory_view
research_memory_hook = render_memory_view
render_research_memory = render_memory
render_research_memory_view = render_memory_view
ResearchMemoryViewModel = MemoryViewModel
MemoryEntryView = MemoryEntry
MemoryFamilyView = MemoryFamily
MemoryPolicyContext = MemoryPolicy


__all__ = [
    "FAMILY_MEMORY_RECORD_TYPE",
    "MEMORY_CONTEXT_RECORD_TYPE",
    "MEMORY_DUPLICATE_DECISION_RECORD_TYPE",
    "MEMORY_ENTRY_RECORD_TYPE",
    "MEMORY_FAMILY_RECORD_TYPE",
    "MEMORY_INTEGRATION_HOOK",
    "MEMORY_POLICY_RECORD_TYPE",
    "FamilyMemory",
    "FamilyMemoryDecision",
    "MemoryAuthority",
    "MemoryDecisions",
    "MemoryDuplicateDecision",
    "MemoryEntry",
    "MemoryEntryView",
    "MemoryFamily",
    "MemoryFamilyView",
    "MemoryFilter",
    "MemoryFilters",
    "MemoryLink",
    "MemoryPolicy",
    "MemoryPolicyContext",
    "MemorySnapshot",
    "MemorySubject",
    "MemoryViewModel",
    "PolicyFact",
    "ResearchMemoryViewModel",
    "build_memory_link",
    "memory_link",
    "memory_view",
    "render_memory",
    "render_memory_view",
    "render_memory_view_model",
    "render_research_memory",
    "render_research_memory_view",
    "research_memory_hook",
]
