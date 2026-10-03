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
                text = f"rank {_text(item.get('rank')) or 'unknown'}"
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
            source_id or kind.title()
        )
        actual_kind = _first_text(item, "kind", "type", "source_kind") or kind
        actual_relation = _first_text(item, "relation", "decision") or relation
    else:
        source_id = _text(value)
        target = None
        label = source_id or kind.title()
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


def _render_links(links: Sequence[MemoryLink], *, relation_label: str = "source") -> str:
    if not links:
        return '<span class="memory-source-missing">Missing / Unconfirmed source</span>'
    rendered: list[str] = []
    for link in links:
        label = f"{link.label} [{link.kind}]"
        relation = (
            f' data-link-relation="{escape(link.relation, quote=True)}"' if link.relation else ""
        )
        if link.target:
            rendered.append(
                f'<a class="memory-link memory-{escape(link.kind, quote=True)}" data-link-kind="{escape(link.kind, quote=True)}"{relation} href="{escape(link.target, quote=True)}">{escape(label)}</a>'
            )
        else:
            rendered.append(
                f'<span class="memory-link-unconfirmed" data-link-kind="{escape(link.kind, quote=True)}"{relation}>{escape(label)} — Missing / Unconfirmed {escape(relation_label)}</span>'
            )
    return '<span class="memory-links">' + " · ".join(rendered) + "</span>"


def _render_facts(title: str, facts: Sequence[PolicyFact], *, section_id: str) -> str:
    if not facts:
        return (
            f'<div class="memory-facts-empty" data-facts="{escape(section_id)}">None recorded</div>'
        )
    rows = "".join(
        f'<div class="memory-fact"><dt>{escape(fact.key)}</dt><dd>{escape(fact.value)}</dd></div>'
        for fact in facts
    )
    return f'<section class="memory-context-section" id="{escape(section_id, quote=True)}"><h3>{escape(title)}</h3><dl>{rows}</dl></section>'


def _render_policy(policy: MemoryPolicy | None, *, heading: str = "Policy context") -> str:
    if policy is None:
        return '<section class="memory-policy" data-memory-object="memory-policy"><h2>Policy context</h2><p>Policy context unavailable / Missing.</p></section>'
    snapshot = policy.snapshot
    snapshot_text = " · ".join(
        part
        for part in (
            f"token {snapshot.token}" if snapshot.token else "token unavailable",
            f"as of {snapshot.as_of}" if snapshot.as_of else "as-of unavailable",
            f"revision {snapshot.revision}" if snapshot.revision else None,
        )
        if part
    )
    rules = "".join(
        f'<div class="memory-fact"><dt>{escape(label)}</dt><dd>{escape(value or "None recorded")}</dd></div>'
        for label, value in (
            ("Inclusion rule", policy.inclusion_rule),
            ("Exclusion rule", policy.exclusion_rule),
        )
    )
    notes = f'<p class="memory-policy-notes">{escape(policy.notes)}</p>' if policy.notes else ""
    return (
        f'<section class="memory-policy" data-memory-object="memory-policy"><h2>{escape(heading)}</h2>'
        f'<p class="memory-policy-id"><strong>Policy</strong> {escape(policy.policy_id)}'
        f"{f' · version {escape(policy.policy_version)}' if policy.policy_version else ''}</p>"
        f'<p class="memory-snapshot"><strong>Snapshot</strong> {escape(snapshot_text or "Unavailable")}</p>'
        f'<dl class="memory-policy-rules">{rules}</dl>'
        f"{_render_facts('Bounds', policy.bounds, section_id='memory-bounds')}"
        f"{_render_facts('Source trust', policy.source_trust, section_id='memory-source-trust')}"
        f"{notes}"
        "</section>"
    )


def _render_decisions(decisions: MemoryDecisions) -> str:
    rows = "".join(
        f'<div class="memory-decision"><dt>{escape(label)}</dt><dd>{escape(value or "None recorded")}</dd></div>'
        for label, value in (
            ("Inclusion decision", decisions.inclusion),
            ("Exclusion decision", decisions.exclusion),
            ("Duplicate decision", decisions.duplicate),
            ("Repeated-equivalent decision", decisions.repeated_equivalent),
            ("Reconciliation decision", decisions.reconciliation),
        )
    )
    return f'<section class="memory-decisions"><h3>Inclusion / exclusion and reconciliation</h3><dl>{rows}</dl></section>'


def _render_subject(subject: MemorySubject) -> str:
    rows = "".join(
        f'<div class="memory-subject-fact"><dt>{escape(label)}</dt><dd>{escape(value or "Missing / Unconfirmed")}</dd></div>'
        for label, value in (
            ("Subject semantic ID", subject.semantic_id),
            ("Structural fingerprint", subject.structural_fingerprint),
            ("Subject label", subject.label),
        )
    )
    return f'<section class="memory-subject"><h3>Subject identity</h3><dl>{rows}</dl></section>'


def _render_entry_detail(entry: MemoryEntry, *, context: QueryContext) -> str:
    relation_sections = "".join(
        (
            f'<section class="memory-relation" data-relation="{relation}"><h3>{escape(label)}</h3>'
            f"{_render_links(getattr(entry, relation), relation_label=label.lower())}</section>"
        )
        for relation, label in (
            ("references", "References"),
            ("conflicts", "Conflicts"),
            ("supersedes", "Supersedes"),
            ("lineage", "Lineage"),
        )
    )
    family = entry.family_label or entry.family_id or "Missing / Unconfirmed"
    summary = entry.safe_summary or "No safe_summary is recorded."
    return (
        f'<article class="memory-detail" data-memory-object="memory-entry" data-memory-entry-id="{escape(entry.memory_id, quote=True)}">'
        f'<p class="eyebrow">memory-entry · Formal Research Memory / GUI read-only</p>'
        f"<h2>{escape(entry.title)}</h2>"
        f'<p class="memory-detail-id"><strong>Memory ID</strong> {escape(entry.memory_id)} · <strong>Family</strong> {escape(family)}</p>'
        f'<p class="memory-safe-summary"><strong>safe_summary</strong> {escape(summary)}</p>'
        f'<dl class="memory-entry-facts">'
        f"<div><dt>Stage</dt><dd>{escape(entry.stage or 'Missing / Unconfirmed')}</dd></div>"
        f"<div><dt>Outcome</dt><dd>{escape(entry.outcome or 'Missing / Unconfirmed')}</dd></div>"
        f"<div><dt>Failure category</dt><dd>{escape(entry.failure_category or 'Missing / Unconfirmed')}</dd></div>"
        f"<div><dt>Campaign</dt><dd>{escape(entry.campaign_id or 'Missing / Unconfirmed')}</dd></div>"
        f"</dl>"
        f"{_render_subject(entry.subject)}"
        f"{relation_sections}"
        f"{_render_decisions(entry.decisions)}"
        f"{_render_policy(entry.policy)}"
        f'<p><a class="memory-back-link" href="{escape(memory_link(query_context=context), quote=True)}">Back to Memory catalog</a></p>'
        "</article>"
    )


def _render_entry_row(entry: MemoryEntry, *, context: QueryContext) -> str:
    family = entry.family_label or entry.family_id or "Missing / Unconfirmed"
    source = _render_links(entry.references, relation_label="reference")
    return (
        f'<tr class="memory-entry-row" data-memory-entry-id="{escape(entry.memory_id, quote=True)}" data-family="{escape(entry.family_id or "", quote=True)}">'
        f'<th scope="row"><a class="memory-entry-link" href="{escape(memory_link(entry.memory_id, query_context=context), quote=True)}">{escape(entry.title)}</a><br><small>{escape(entry.memory_id)}</small></th>'
        f"<td>{escape(family)}</td><td>{escape(entry.stage or 'Missing / Unconfirmed')}</td>"
        f"<td>{escape(entry.outcome or 'Missing / Unconfirmed')}</td><td>{escape(entry.failure_category or 'Missing / Unconfirmed')}</td>"
        f"<td>{escape(entry.subject.semantic_id or 'Missing / Unconfirmed')}</td><td>{source}</td></tr>"
    )


def _render_filters(view: MemoryViewModel, *, context: QueryContext) -> str:
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
    for key in _MEMORY_FILTER_KEYS:
        choices = "".join(
            f'<option value="{escape(choice, quote=True)}"{(" selected" if values[key] == choice else "")}>{escape(choice)}</option>'
            for choice in options[key]
        )
        controls.append(
            f'<label>{escape(key.replace("_", " ").title())} <select name="{escape(key, quote=True)}"><option value="">All</option>{choices}</select></label>'
        )
    return (
        '<form class="memory-filters" action="/" method="get" aria-label="Research Memory filters">'
        '<input type="hidden" name="view" value="memory">'
        f"{hidden}{''.join(controls)}"
        '<button type="submit">Apply filters</button><a class="memory-clear" href="/?view=memory">Clear</a></form>'
    )


def _render_family_memories(view: MemoryViewModel) -> str:
    if not view.family_memories:
        return ""
    sections: list[str] = []
    for memory in view.family_memories:
        decisions = (
            "".join(
                f'<li data-entry-id="{escape(decision.entry_id or "", quote=True)}">'
                f"<strong>{escape('Included' if decision.included is True else 'Excluded' if decision.included is False else 'Undetermined')}</strong> "
                f"{escape(decision.entry_id or 'Missing / Unconfirmed')}"
                f"{f' · {escape(decision.reason)}' if decision.reason else ''}</li>"
                for decision in memory.decisions
            )
            or "<li>None recorded.</li>"
        )
        sections.append(
            f'<article class="family-memory" data-memory-object="family-memory" data-family-memory-id="{escape(memory.memory_id, quote=True)}">'
            f"<h3>family-memory {escape(memory.memory_id)}</h3>"
            f"<p><strong>Target family</strong> {escape(memory.target_family_id or 'Missing / Unconfirmed')} · "
            f"<strong>Policy</strong> {escape(memory.policy_id or 'Missing / Unconfirmed')} · "
            f"<strong>Snapshot</strong> {escape(memory.snapshot_token or 'Unavailable')}</p>"
            f"<h4>Inclusion / exclusion decisions</h4><ul>{decisions}</ul>"
            f"<p>{_render_links(memory.lineage, relation_label='lineage')}</p></article>"
        )
    return (
        '<section class="memory-family-memory"><h2>Family-memory snapshots</h2>'
        + "".join(sections)
        + "</section>"
    )


def _render_duplicate_decisions(view: MemoryViewModel) -> str:
    if not view.duplicate_decisions:
        return ""
    rows = "".join(
        f'<li data-decision-id="{escape(decision.decision_id, quote=True)}"><strong>{escape(decision.disposition)}</strong> '
        f"{escape(decision.decision_id)} · matched {len(decision.matched_entry_ids)} entries"
        f"{f' · semantic {escape(decision.subject_semantic_id)}' if decision.subject_semantic_id else ''}"
        f"{f' · fingerprint {escape(decision.structural_fingerprint)}' if decision.structural_fingerprint else ''}"
        f" {_render_links(decision.lineage, relation_label='lineage')}</li>"
        for decision in view.duplicate_decisions
    )
    return (
        '<section class="memory-duplicate-decisions"><h2>Duplicate / repeated-equivalent / reconciliation decisions</h2><ul>'
        + rows
        + "</ul></section>"
    )


def _render_families(view: MemoryViewModel, *, context: QueryContext) -> str:
    if not view.families:
        return '<section class="memory-families" data-memory-object="memory-family"><h2>Memory families</h2><p>None recorded.</p></section>'
    items = "".join(
        f'<li data-family-id="{escape(family.family_id, quote=True)}"><strong>{escape(family.label)}</strong> '
        f"<span>{escape(family.family_id)} · {len(family.entry_ids)} entries</span>"
        f"{f'<span> · Campaign {escape(family.campaign_id)}</span>' if family.campaign_id else ''}"
        f'<a href="{escape(memory_link(query_context=context, filters=MemoryFilters(family=family.family_id)), quote=True)}">Open family-memory</a>'
        f"{_render_links(family.lineage, relation_label='lineage')}</li>"
        for family in view.families
    )
    return f'<section class="memory-families" data-memory-object="memory-family"><h2>Memory families / family-memory</h2><ul>{items}</ul></section>'


def _render_policy_index(view: MemoryViewModel) -> str:
    if not view.policies:
        return '<section class="memory-policy-index"><h2>Memory policies</h2><p>None recorded.</p></section>'
    items = "".join(
        f'<li data-policy-id="{escape(policy.policy_id, quote=True)}"><strong>{escape(policy.policy_id)}</strong>'
        f"{f' · version {escape(policy.policy_version)}' if policy.policy_version else ''} · {len(policy.bounds)} bounds · {len(policy.source_trust)} source-trust facts</li>"
        for policy in view.policies
    )
    return (
        f'<section class="memory-policy-index"><h2>Memory policies</h2><ul>{items}</ul></section>'
    )


def _render_derivation(model: ManagerReadModel, *, sample_count: int) -> str:
    derivation = model.derivation
    if derivation.kind == "direct":
        return ""
    inputs = ", ".join(derivation.inputs) if derivation.inputs else "None recorded"
    return (
        '<section class="memory-derived-context" data-memory-derived="true"><h2>GUI Derived view context</h2>'
        f"<dl><div><dt>Derivation kind</dt><dd>{escape(derivation.kind)}</dd></div>"
        f"<div><dt>Rule</dt><dd>{escape(derivation.rule or 'Missing / Unconfirmed')}</dd></div>"
        f"<div><dt>Named inputs</dt><dd>{escape(inputs)}</dd></div>"
        f"<div><dt>Version</dt><dd>{escape(derivation.version or 'Missing / Unconfirmed')}</dd></div>"
        f"<div><dt>Sample count</dt><dd>{sample_count}</dd></div></dl>"
        "<p>This reproducible GUI projection is not a formal Research Memory publication.</p></section>"
    )


def render_memory(
    view_or_model: MemoryViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    memory_id: str | None = None,
) -> str:
    """Render a Memory catalog/detail fragment; the shared shell owns document chrome."""

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
    source_text = ", ".join(source.source_id for source in model.source_refs) or "None recorded"
    authority_copy = (
        "GUI Derived view — reproducibly shaped from named read-model inputs; it is not formal Research Memory."
        if view.is_derived
        else "Formal Research Memory — owner-published entries only; ordinary records are not promoted."
    )
    pieces = [
        '<section class="research-memory" data-integration-hook="memory-view" '
        f'data-memory-authority="{view.authority.value}" data-memory-empty="{"true" if view.empty else "false"}">',
        '<p class="eyebrow">Research Memory · read-only</p>',
        '<h1 class="page-title" data-page-title tabindex="-1">Research Memory</h1>',
        f'<p class="memory-authority" data-memory-authority-label="{view.authority.value}"><strong>{escape("GUI Derived" if view.is_derived else "Formal Research Memory")}</strong> {escape(authority_copy)}</p>',
        f'<p class="context-line memory-context"><span><strong>Observed</strong> {escape(model.as_of or "Unavailable")}</span>'
        f"<span><strong>Snapshot</strong> {escape(model.snapshot_token or 'Unavailable')}</span><span><strong>Sources</strong> {escape(source_text)}</span></p>",
        render_status_block(model),
    ]
    if view.is_derived:
        pieces.append(_render_derivation(model, sample_count=len(view.entries)))
    if view.empty:
        detail = (
            "No formal Research Memory entries are recorded. No published Research Memory entries are available; ordinary records are not inferred as Memory."
            if not view.explicit_memory_payload
            else "No Research Memory entries are recorded in this scope. No published Research Memory entries are available in this snapshot."
        )
        if model.availability.status in {ReadModelStatus.MISSING, ReadModelStatus.KNOWN}:
            pieces.append(render_operational_state(DisplayState.EMPTY, detail=detail))
        else:
            pieces.append(
                f'<p class="memory-empty-not-determined" data-memory-empty-state="not-determined">'
                f"{escape(detail)} Availability is {escape(model.availability.status.value)}; this is not evidence that Memory is empty.</p>"
            )
    if model.availability.status is ReadModelStatus.KNOWN and not model.availability.complete:
        pieces.append(
            '<p class="memory-partial-note">Partial Memory scope: unavailable entries are not filled in.</p>'
        )
    pieces.append(_render_filters(view, context=context))
    selected = view.selected_entry
    if view.selected_memory_id is not None and selected is None:
        pieces.append(
            f'<section class="memory-detail-missing" data-memory-detail="missing"><h2>Memory entry unavailable</h2>'
            f"<p>{escape(view.selected_memory_id)} — Missing / Unconfirmed in this snapshot.</p></section>"
        )
    elif selected is not None:
        pieces.append(_render_entry_detail(selected, context=context))
    if view.entries:
        rows = "".join(_render_entry_row(entry, context=context) for entry in view.entries)
        pieces.append(
            '<section class="memory-catalog" data-memory-object="memory-entry"><h2>Memory-entry catalog</h2>'
            "<table><caption>Explicit Research Memory entries</caption><thead><tr>"
            '<th scope="col">Memory entry</th><th scope="col">Family</th><th scope="col">Stage</th>'
            '<th scope="col">Outcome</th><th scope="col">Failure category</th><th scope="col">Subject semantic ID</th><th scope="col">References</th>'
            f"</tr></thead><tbody>{rows}</tbody></table></section>"
        )
    pieces.append(_render_families(view, context=context))
    pieces.append(_render_family_memories(view))
    pieces.append(_render_duplicate_decisions(view))
    pieces.append(_render_policy_index(view))
    policy = (
        selected.policy if selected is not None else (view.policies[0] if view.policies else None)
    )
    pieces.append(_render_policy(policy, heading="Active policy context"))
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
