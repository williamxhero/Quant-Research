"""Research Memory visibility and applicability gates.

This module implements the local, deterministic gate used before any protected
Research Memory material is resolved for a consumer.  The request is metadata
only; payload loading is deliberately a second step that runs only after the
gate returns an allowed decision.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from .core import AcceptanceFailure

VisibilityMode = Literal["strict", "audit"]
VisibilityStatus = Literal["allowed", "restricted", "unknown"]
DeliveryStatus = Literal["delivered", "restricted", "unavailable"]
SafetyAuditStatus = Literal["not_applicable", "clear", "unknown", "blocked"]

VISIBILITY_REQUEST_SCHEMA = "quant-research.memory-visibility-request.v1"
VISIBILITY_DECISION_SCHEMA = "quant-research.memory-visibility-decision.v1"

DEFAULT_PROTECTION_CLOSURE_BUDGET = 64
MAX_PROTECTION_CLOSURE_BUDGET = 4096

_STAGES = frozenset(
    {
        "initial_read",
        "ranking",
        "embedding",
        "summary",
        "planning",
        "research_model",
        "final_envelope",
        "tool_return",
        "historical_redelivery",
    }
)
_ADDITION_STAGES = frozenset({"final_envelope", "tool_return"})
# Codes that mean "the declared protection closure is not provably complete".
# They are never deliverable; audit mode may report them as ``unknown`` but that
# is a reporting state, not research eligibility.
_INCOMPLETE_CODES = frozenset(
    {
        "metadata_incomplete",
        "lineage_metadata_incomplete",
        "closure_incomplete",
        "closure_budget_exhausted",
    }
)
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}")
_SAFE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_MATERIAL_FIELDS = frozenset(
    {
        "material_id",
        "record_type",
        "logical_dataset",
        "universe",
        "time_range",
        "sample_role",
        "derived_from",
        "allowed_purposes",
        "required_capabilities",
        "content_digest",
        "display_name",
        "campaign_id",
        "dataset_version",
    }
)
_LINEAGE_FIELDS = frozenset(
    {
        "material_id",
        "relationship",
        "logical_dataset",
        "universe",
        "time_range",
        "sample_role",
    }
)


@dataclass(frozen=True, slots=True)
class LogicalTimeRange:
    start: str
    end: str

    @classmethod
    def parse(cls, value: object, label: str) -> tuple[LogicalTimeRange | None, tuple[str, ...]]:
        if not isinstance(value, Mapping):
            return None, (f"{label}.time_range",)
        _fields_subset(value, {"start", "end"}, f"{label}.time_range")
        missing: list[str] = []
        start = _optional_token(value.get("start"), f"{label}.time_range.start", missing)
        end = _optional_token(value.get("end"), f"{label}.time_range.end", missing)
        if missing:
            return None, tuple(missing)
        if end < start:
            raise AcceptanceFailure(f"{label}.time_range is invalid")
        return cls(start, end), ()

    def contains(self, other: LogicalTimeRange) -> bool:
        return self.start <= other.start and other.end <= self.end

    def as_dict(self) -> dict[str, str]:
        return {"start": self.start, "end": self.end}


@dataclass(frozen=True, slots=True)
class LogicalScope:
    logical_dataset: str
    universe: tuple[str, ...]
    time_range: LogicalTimeRange
    sample_role: str

    @classmethod
    def parse(
        cls, value: Mapping[str, object], label: str
    ) -> tuple[LogicalScope | None, tuple[str, ...]]:
        missing: list[str] = []
        dataset = _optional_token(value.get("logical_dataset"), f"{label}.logical_dataset", missing)
        universe = _optional_tokens(value.get("universe"), f"{label}.universe", missing)
        time_range, range_missing = LogicalTimeRange.parse(value.get("time_range"), label)
        missing.extend(range_missing)
        role = _optional_token(value.get("sample_role"), f"{label}.sample_role", missing)
        if missing:
            return None, tuple(missing)
        if time_range is None:
            raise AssertionError("time range cannot be missing when scope is complete")
        return cls(dataset, universe, time_range, role), ()

    def as_dict(self) -> dict[str, object]:
        return {
            "logical_dataset": self.logical_dataset,
            "universe": list(self.universe),
            "time_range": self.time_range.as_dict(),
            "sample_role": self.sample_role,
        }

    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class LineageScope:
    material_id: str
    relationship: str
    scope: LogicalScope | None
    missing_fields: tuple[str, ...]

    @classmethod
    def parse(cls, value: object, index: int) -> LineageScope:
        label = f"derived_from[{index}]"
        item = _mapping(value, label)
        _fields_subset(item, _LINEAGE_FIELDS, label)
        scope, missing = LogicalScope.parse(item, label)
        return cls(
            material_id=_token(item.get("material_id"), f"{label}.material_id"),
            relationship=_token(item.get("relationship"), f"{label}.relationship"),
            scope=scope,
            missing_fields=missing,
        )

    def digest(self) -> str:
        scope = None if self.scope is None else self.scope.as_dict()
        return _digest(
            {
                "material_id": self.material_id,
                "relationship": self.relationship,
                "scope": scope,
                "missing_fields": list(self.missing_fields),
            }
        )


@dataclass(frozen=True, slots=True)
class ResearchMaterial:
    material_id: str
    record_type: str
    scope: LogicalScope | None
    missing_scope_fields: tuple[str, ...]
    missing_metadata_fields: tuple[str, ...]
    derived_from: tuple[LineageScope, ...]
    allowed_purposes: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    content_digest: str | None
    display_name: str | None
    campaign_id: str | None
    dataset_version: str | None

    @classmethod
    def parse(cls, value: object, index: int) -> ResearchMaterial:
        label = f"materials[{index}]"
        item = _mapping(value, label)
        _fields_subset(item, _MATERIAL_FIELDS, label)
        scope, missing = LogicalScope.parse(item, label)
        missing_metadata: list[str] = []
        raw_lineage = item.get("derived_from")
        if raw_lineage is None:
            missing_metadata.append(f"{label}.derived_from")
            derived_from: tuple[LineageScope, ...] = ()
        else:
            derived_from = tuple(
                LineageScope.parse(raw, lineage_index)
                for lineage_index, raw in enumerate(_list(raw_lineage, f"{label}.derived_from"))
            )
        raw_purposes = item.get("allowed_purposes")
        if raw_purposes is None:
            missing_metadata.append(f"{label}.allowed_purposes")
            allowed_purposes: tuple[str, ...] = ()
        else:
            allowed_purposes = _tokens(raw_purposes, f"{label}.allowed_purposes")
        raw_capabilities = item.get("required_capabilities")
        if raw_capabilities is None:
            missing_metadata.append(f"{label}.required_capabilities")
            required_capabilities: tuple[str, ...] = ()
        else:
            required_capabilities = _tokens(
                raw_capabilities,
                f"{label}.required_capabilities",
                empty=True,
            )
        digest = item.get("content_digest")
        if digest is not None and (
            not isinstance(digest, str) or _SAFE_DIGEST.fullmatch(digest) is None
        ):
            raise AcceptanceFailure(f"{label}.content_digest is invalid")
        return cls(
            material_id=_token(item.get("material_id"), f"{label}.material_id"),
            record_type=_token(item.get("record_type"), f"{label}.record_type"),
            scope=scope,
            missing_scope_fields=missing,
            missing_metadata_fields=tuple(missing_metadata),
            derived_from=derived_from,
            allowed_purposes=allowed_purposes,
            required_capabilities=required_capabilities,
            content_digest=digest,
            display_name=_optional_label(item.get("display_name"), f"{label}.display_name"),
            campaign_id=_optional_label(item.get("campaign_id"), f"{label}.campaign_id"),
            dataset_version=_optional_label(
                item.get("dataset_version"),
                f"{label}.dataset_version",
            ),
        )

    def protected_scope_digests(self) -> tuple[str, ...]:
        scopes = [self.scope.digest()] if self.scope is not None else []
        scopes.extend(lineage.scope.digest() for lineage in self.derived_from if lineage.scope)
        return tuple(sorted(set(scopes)))


@dataclass(frozen=True, slots=True)
class AccessGrant:
    logical_dataset: str
    universe: tuple[str, ...]
    time_range: LogicalTimeRange
    sample_roles: tuple[str, ...]
    purposes: tuple[str, ...]

    @classmethod
    def parse(cls, value: object, index: int) -> AccessGrant:
        label = f"consumer.grants[{index}]"
        item = _mapping(value, label)
        _fields_subset(
            item,
            {"logical_dataset", "universe", "time_range", "sample_roles", "purposes"},
            label,
        )
        scope, missing = LogicalScope.parse(
            {
                "logical_dataset": item.get("logical_dataset"),
                "universe": item.get("universe"),
                "time_range": item.get("time_range"),
                "sample_role": "grant-placeholder",
            },
            label,
        )
        if scope is None:
            raise AcceptanceFailure(f"{label} scope is incomplete: {','.join(missing)}")
        return cls(
            logical_dataset=scope.logical_dataset,
            universe=scope.universe,
            time_range=scope.time_range,
            sample_roles=_tokens(item.get("sample_roles"), f"{label}.sample_roles"),
            purposes=_tokens(item.get("purposes"), f"{label}.purposes"),
        )

    def covers(self, scope: LogicalScope, purpose: str) -> bool:
        return (
            self.logical_dataset == scope.logical_dataset
            and set(scope.universe) <= set(self.universe)
            and self.time_range.contains(scope.time_range)
            and scope.sample_role in self.sample_roles
            and purpose in self.purposes
        )

    def digest(self) -> str:
        return _digest(
            {
                "logical_dataset": self.logical_dataset,
                "universe": list(self.universe),
                "time_range": self.time_range.as_dict(),
                "sample_roles": list(self.sample_roles),
                "purposes": list(self.purposes),
            }
        )


@dataclass(frozen=True, slots=True)
class CurrentConsumerAccess:
    actor_id: str
    consumer: str
    action: str
    purpose: str
    capabilities: tuple[str, ...]
    authorization_policy_id: str
    authorization_policy_version: str
    authorization_knowledge_cutoff: str
    grants: tuple[AccessGrant, ...]

    @classmethod
    def parse(cls, value: object) -> CurrentConsumerAccess:
        item = _mapping(value, "consumer")
        _fields_subset(
            item,
            {
                "actor_id",
                "consumer",
                "action",
                "purpose",
                "capabilities",
                "authorization_policy_id",
                "authorization_policy_version",
                "authorization_knowledge_cutoff",
                "grants",
            },
            "consumer",
        )
        return cls(
            actor_id=_token(item.get("actor_id"), "consumer.actor_id"),
            consumer=_token(item.get("consumer"), "consumer.consumer"),
            action=_token(item.get("action"), "consumer.action"),
            purpose=_token(item.get("purpose"), "consumer.purpose"),
            capabilities=_tokens(item.get("capabilities"), "consumer.capabilities", empty=True),
            authorization_policy_id=_token(
                item.get("authorization_policy_id"),
                "consumer.authorization_policy_id",
            ),
            authorization_policy_version=_token(
                item.get("authorization_policy_version"),
                "consumer.authorization_policy_version",
            ),
            authorization_knowledge_cutoff=_token(
                item.get("authorization_knowledge_cutoff"),
                "consumer.authorization_knowledge_cutoff",
            ),
            grants=tuple(
                AccessGrant.parse(raw, index)
                for index, raw in enumerate(_list(item.get("grants", []), "consumer.grants"))
            ),
        )

    def has_current_grant(self, scope: LogicalScope) -> bool:
        return any(grant.covers(scope, self.purpose) for grant in self.grants)

    def sanitized(self, status: VisibilityStatus) -> dict[str, object]:
        return {
            "actor_digest": _digest({"actor_id": self.actor_id}),
            "consumer": self.consumer,
            "action": self.action,
            "purpose": self.purpose,
            "authorization_policy": {
                "policy_id": self.authorization_policy_id,
                "policy_version": self.authorization_policy_version,
                "knowledge_cutoff": self.authorization_knowledge_cutoff,
            },
            "grant_digests": [grant.digest() for grant in self.grants],
            "status": status,
        }


@dataclass(frozen=True, slots=True)
class FrozenResearchPolicy:
    policy_id: str
    policy_version: str
    knowledge_cutoff: str
    permitted_sample_roles: tuple[str, ...]
    permitted_purposes: tuple[str, ...]

    @classmethod
    def parse(cls, value: object) -> FrozenResearchPolicy:
        item = _mapping(value, "research_policy")
        _fields_subset(
            item,
            {
                "policy_id",
                "policy_version",
                "knowledge_cutoff",
                "permitted_sample_roles",
                "permitted_purposes",
            },
            "research_policy",
        )
        return cls(
            policy_id=_token(item.get("policy_id"), "research_policy.policy_id"),
            policy_version=_token(item.get("policy_version"), "research_policy.policy_version"),
            knowledge_cutoff=_token(
                item.get("knowledge_cutoff"), "research_policy.knowledge_cutoff"
            ),
            permitted_sample_roles=_tokens(
                item.get("permitted_sample_roles"),
                "research_policy.permitted_sample_roles",
            ),
            permitted_purposes=_tokens(
                item.get("permitted_purposes"),
                "research_policy.permitted_purposes",
            ),
        )

    def permits(self, scope: LogicalScope, purpose: str) -> bool:
        return (
            scope.sample_role in self.permitted_sample_roles and purpose in self.permitted_purposes
        )

    def sanitized(self, status: VisibilityStatus) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "knowledge_cutoff": self.knowledge_cutoff,
            "status": status,
        }


@dataclass(frozen=True, slots=True)
class HistoricalContextRef:
    context_id: str
    original_actor_id: str
    original_authorization_policy_id: str
    original_decision: VisibilityStatus

    @classmethod
    def parse(cls, value: object) -> HistoricalContextRef | None:
        if value is None:
            return None
        item = _mapping(value, "historical_context")
        _fields_subset(
            item,
            {
                "context_id",
                "original_actor_id",
                "original_authorization_policy_id",
                "original_decision",
            },
            "historical_context",
        )
        decision = _token(item.get("original_decision"), "historical_context.original_decision")
        if decision not in {"allowed", "restricted", "unknown"}:
            raise AcceptanceFailure("historical_context.original_decision is invalid")
        return cls(
            context_id=_token(item.get("context_id"), "historical_context.context_id"),
            original_actor_id=_token(
                item.get("original_actor_id"),
                "historical_context.original_actor_id",
            ),
            original_authorization_policy_id=_token(
                item.get("original_authorization_policy_id"),
                "historical_context.original_authorization_policy_id",
            ),
            original_decision=decision,  # type: ignore[arg-type]
        )

    def digest(self) -> str:
        return _digest(
            {
                "context_id": self.context_id,
                "original_actor_id": self.original_actor_id,
                "original_authorization_policy_id": self.original_authorization_policy_id,
                "original_decision": self.original_decision,
            }
        )


@dataclass(frozen=True, slots=True)
class VisibilityRequest:
    stage: str
    mode: VisibilityMode
    consumer: CurrentConsumerAccess
    research_policy: FrozenResearchPolicy
    materials: tuple[ResearchMaterial, ...]
    context_material_ids: tuple[str, ...]
    historical_context: HistoricalContextRef | None
    closure_budget: int

    @classmethod
    def parse(cls, value: Mapping[str, object]) -> VisibilityRequest:
        _fields_subset(
            value,
            {
                "schema",
                "stage",
                "mode",
                "consumer",
                "research_policy",
                "materials",
                "context_material_ids",
                "historical_context",
                "closure_budget",
            },
            "visibility request",
        )
        if value.get("schema") != VISIBILITY_REQUEST_SCHEMA:
            raise AcceptanceFailure("visibility request schema is invalid")
        stage = _token(value.get("stage"), "visibility request stage")
        if stage not in _STAGES:
            raise AcceptanceFailure(f"visibility stage is invalid: {stage}")
        mode = _token(value.get("mode"), "visibility request mode")
        if mode not in {"strict", "audit"}:
            raise AcceptanceFailure(f"visibility mode is invalid: {mode}")
        materials = tuple(
            ResearchMaterial.parse(raw, index)
            for index, raw in enumerate(_list(value.get("materials"), "materials"))
        )
        if not materials:
            raise AcceptanceFailure("visibility request contains no materials")
        material_ids = [material.material_id for material in materials]
        if len(material_ids) != len(set(material_ids)):
            raise AcceptanceFailure("visibility material ids are not unique")
        return cls(
            stage=stage,
            mode=mode,  # type: ignore[arg-type]
            consumer=CurrentConsumerAccess.parse(value.get("consumer")),
            research_policy=FrozenResearchPolicy.parse(value.get("research_policy")),
            materials=materials,
            context_material_ids=_tokens(
                value.get("context_material_ids", []),
                "context_material_ids",
                empty=True,
            ),
            historical_context=HistoricalContextRef.parse(value.get("historical_context")),
            closure_budget=_closure_budget(value.get("closure_budget")),
        )

    def added_material_ids(self) -> tuple[str, ...]:
        """Material ids in this request that the declared Context does not carry."""

        context = set(self.context_material_ids)
        return tuple(
            material.material_id
            for material in self.materials
            if material.material_id not in context
        )

    def safe_identity_material(self) -> dict[str, object]:
        return {
            "schema": VISIBILITY_REQUEST_SCHEMA,
            "stage": self.stage,
            "mode": self.mode,
            "consumer": {
                **self.consumer.sanitized("unknown"),
                "capabilities_digest": _digest(list(self.consumer.capabilities)),
            },
            "research_policy": {
                **self.research_policy.sanitized("unknown"),
                "rule_digest": _digest(
                    {
                        "permitted_sample_roles": list(self.research_policy.permitted_sample_roles),
                        "permitted_purposes": list(self.research_policy.permitted_purposes),
                    }
                ),
            },
            "materials": [
                {
                    "material_id": material.material_id,
                    "record_type": material.record_type,
                    "scope_digests": list(material.protected_scope_digests()),
                    "scope_missing_fields": list(material.missing_scope_fields),
                    "metadata_missing_fields": list(material.missing_metadata_fields),
                    "lineage_digests": [lineage.digest() for lineage in material.derived_from],
                    "allowed_purposes": list(material.allowed_purposes),
                    "required_capabilities": list(material.required_capabilities),
                    "content_digest": material.content_digest,
                }
                for material in self.materials
            ],
            "context_material_ids": list(self.context_material_ids),
            "historical_context_digest": (
                None if self.historical_context is None else self.historical_context.digest()
            ),
            "closure_budget": self.closure_budget,
        }


@dataclass(frozen=True, slots=True)
class MaterialVisibilityDecision:
    material_id: str
    record_type: str
    status: VisibilityStatus
    safe_codes: tuple[str, ...]
    scope_digests: tuple[str, ...]
    lineage_digests: tuple[str, ...]
    closure_digest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "material_id": self.material_id,
            "record_type": self.record_type,
            "status": self.status,
            "safe_codes": list(self.safe_codes),
            "scope_digests": list(self.scope_digests),
            "lineage_digests": list(self.lineage_digests),
            "closure_digest": self.closure_digest,
        }


@dataclass(frozen=True, slots=True)
class GateDecision:
    status: VisibilityStatus
    stage: str
    mode: VisibilityMode
    request_identity: str
    current_access: dict[str, object]
    research_policy: dict[str, object]
    materials: tuple[MaterialVisibilityDecision, ...]
    historical_context_digest: str | None
    safety_audit: dict[str, object]

    @property
    def deliverable(self) -> bool:
        return self.status == "allowed"

    def as_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "schema": VISIBILITY_DECISION_SCHEMA,
            "status": self.status,
            "deliverable": self.deliverable,
            "stage": self.stage,
            "mode": self.mode,
            "request_identity": self.request_identity,
            "current_access": self.current_access,
            "research_policy": self.research_policy,
            "historical_context_digest": self.historical_context_digest,
            "safety_audit": self.safety_audit,
        }
        # A denied response is observable by an untrusted consumer.  Do not turn
        # the decision itself into a reference, count, lineage, or reason oracle.
        # The detailed per-material facts remain available only on the in-process
        # decision object for the trusted policy/audit boundary.
        if self.deliverable:
            value["materials"] = [material.as_dict() for material in self.materials]
        else:
            value["delivery"] = "blocked"
        return value


@dataclass(frozen=True, slots=True)
class GuardedDelivery:
    decision: GateDecision
    payloads: tuple[tuple[str, object], ...]
    delivery_status: DeliveryStatus

    def as_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "decision": self.decision.as_dict(),
            "delivery_status": self.delivery_status,
        }
        if self.delivery_status == "delivered":
            value["payload_count"] = len(self.payloads)
            value["material_ids"] = [material_id for material_id, _payload in self.payloads]
        return value


class VisibilityGate:
    """Fail-closed metadata gate for Research Memory material delivery."""

    def evaluate(self, request: VisibilityRequest | Mapping[str, object]) -> GateDecision:
        parsed = (
            request if isinstance(request, VisibilityRequest) else VisibilityRequest.parse(request)
        )
        material_decisions = tuple(
            self._evaluate_material(parsed, material) for material in parsed.materials
        )
        status = _overall_status(tuple(item.status for item in material_decisions))
        current_status = _dimension_status(
            material_decisions,
            denied_codes={
                "current_authorization_denied",
                "lineage_current_authorization_denied",
                "capability_denied",
                "purpose_denied",
            },
        )
        policy_status = _dimension_status(
            material_decisions,
            denied_codes={"research_policy_denied", "lineage_research_policy_denied"},
        )
        return GateDecision(
            status=status,
            stage=parsed.stage,
            mode=parsed.mode,
            request_identity=_digest(parsed.safe_identity_material()),
            current_access=parsed.consumer.sanitized(current_status),
            research_policy=parsed.research_policy.sanitized(policy_status),
            materials=material_decisions,
            historical_context_digest=(
                None if parsed.historical_context is None else parsed.historical_context.digest()
            ),
            safety_audit=_safety_audit(parsed, material_decisions),
        )

    def _evaluate_material(
        self,
        request: VisibilityRequest,
        material: ResearchMaterial,
    ) -> MaterialVisibilityDecision:
        codes: set[str] = set()
        if material.missing_scope_fields or material.missing_metadata_fields:
            codes.add("metadata_incomplete")
        closure_scopes, closure_codes, closure_digest = _protection_closure(request, material)
        codes.update(closure_codes)
        if (
            not any(
                field.endswith(".allowed_purposes") for field in material.missing_metadata_fields
            )
            and request.consumer.purpose not in material.allowed_purposes
        ):
            codes.add("purpose_denied")
        if not any(
            field.endswith(".required_capabilities") for field in material.missing_metadata_fields
        ) and not set(material.required_capabilities) <= set(request.consumer.capabilities):
            codes.add("capability_denied")
        if material.scope is not None:
            _check_scope(request, material.scope, codes, lineage=False)
        for scope in closure_scopes:
            _check_scope(request, scope, codes, lineage=True)
        safe_codes = tuple(sorted(codes))
        return MaterialVisibilityDecision(
            material_id=material.material_id,
            record_type=material.record_type,
            status=_material_status(safe_codes, request.mode),
            safe_codes=safe_codes,
            scope_digests=material.protected_scope_digests(),
            lineage_digests=tuple(lineage.digest() for lineage in material.derived_from),
            closure_digest=closure_digest,
        )


def evaluate_visibility_request(value: Mapping[str, object]) -> GateDecision:
    return VisibilityGate().evaluate(value)


def guard_visibility_delivery(
    request: VisibilityRequest | Mapping[str, object],
    load_material: Callable[[str], object],
) -> GuardedDelivery:
    parsed = request if isinstance(request, VisibilityRequest) else VisibilityRequest.parse(request)
    decision = VisibilityGate().evaluate(parsed)
    if not decision.deliverable:
        return GuardedDelivery(decision, (), "restricted")
    try:
        payloads = tuple(
            (material.material_id, load_material(material.material_id))
            for material in parsed.materials
        )
    except Exception:
        # Loader diagnostics can contain protected source text, identifiers, or
        # provider debug state.  The public delivery boundary reports only that
        # delivery is unavailable; the trusted loader owns detailed diagnostics.
        return GuardedDelivery(decision, (), "unavailable")
    return GuardedDelivery(decision, payloads, "delivered")


def _canonical_edges(edges: tuple[LineageScope, ...]) -> tuple[LineageScope, ...]:
    """Deduplicate and order derivation edges so repeats cannot change a decision."""

    unique: dict[str, LineageScope] = {}
    for edge in edges:
        unique.setdefault(edge.digest(), edge)
    return tuple(edge for _digest, edge in sorted(unique.items()))


def _protection_closure(
    request: VisibilityRequest,
    material: ResearchMaterial,
) -> tuple[tuple[LogicalScope, ...], tuple[str, ...], str]:
    """Walk the declared derivation closure of one material, fail closed.

    Protection propagates along every hop that the request declares, so a
    multi-hop chain cannot be laundered by re-publishing a derived record.  The
    walk is bounded by the request's frozen traversal budget: an exhausted
    budget, an unresolvable hop, or a non-acyclic lineage yields a defect code
    rather than an empty closure.  Reachability alone never grants eligibility.
    """

    declared = {item.material_id: item for item in request.materials}
    codes: set[str] = set()
    scopes: dict[str, LogicalScope] = {}
    members: set[str] = {material.material_id}
    on_path: set[str] = {material.material_id}
    visits = 0
    # Explicit-stack DFS; each frame is [node_id, depth, edges, next_index].
    frames: list[list[Any]] = [
        [material.material_id, 0, _canonical_edges(material.derived_from), 0]
    ]
    while frames:
        frame = frames[-1]
        node_id, depth, edges, index = frame
        if index >= len(edges):
            frames.pop()
            on_path.discard(node_id)
            continue
        frame[3] = index + 1
        edge = edges[index]
        visits += 1
        if visits > request.closure_budget:
            codes.add("closure_budget_exhausted")
            break
        members.add(edge.digest())
        if edge.scope is None:
            codes.add("lineage_metadata_incomplete" if depth == 0 else "closure_incomplete")
        else:
            scopes[edge.scope.digest()] = edge.scope
        if edge.material_id in on_path:
            codes.add("closure_not_acyclic")
            continue
        child = declared.get(edge.material_id)
        if child is None:
            continue
        if child.missing_scope_fields or child.missing_metadata_fields:
            codes.add("closure_incomplete")
        if child.scope is not None:
            scopes[child.scope.digest()] = child.scope
        on_path.add(child.material_id)
        frames.append([child.material_id, depth + 1, _canonical_edges(child.derived_from), 0])
    return (
        tuple(scopes[key] for key in sorted(scopes)),
        tuple(sorted(codes)),
        _digest(sorted(members)),
    )


def _safety_audit(
    request: VisibilityRequest,
    decisions: tuple[MaterialVisibilityDecision, ...],
) -> dict[str, object]:
    """Report how post-assembly additions were handled, without result detail.

    A Context draft passing the gate does not carry the final envelope or a tool
    return: material the Context does not declare is re-checked here and gets an
    explicit status, so a blocked addition is neither silently dropped nor
    silently delivered.
    """

    if request.stage not in _ADDITION_STAGES:
        return {"stage": request.stage, "scope": "context_only", "status": "not_applicable"}
    added = set(request.added_material_ids())
    if not added:
        return {"stage": request.stage, "scope": "context_only", "status": "clear"}
    statuses = {item.status for item in decisions if item.material_id in added}
    if "restricted" in statuses:
        status: SafetyAuditStatus = "blocked"
    elif "unknown" in statuses:
        status = "unknown"
    else:
        status = "clear"
    return {"stage": request.stage, "scope": "envelope_addition", "status": status}


def _closure_budget(value: object) -> int:
    if value is None:
        return DEFAULT_PROTECTION_CLOSURE_BUDGET
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= MAX_PROTECTION_CLOSURE_BUDGET
    ):
        raise AcceptanceFailure("visibility request closure_budget is invalid")
    return value


def _check_scope(
    request: VisibilityRequest,
    scope: LogicalScope,
    codes: set[str],
    *,
    lineage: bool,
) -> None:
    if not request.consumer.has_current_grant(scope):
        codes.add(
            "lineage_current_authorization_denied" if lineage else "current_authorization_denied"
        )
    if not request.research_policy.permits(scope, request.consumer.purpose):
        codes.add("lineage_research_policy_denied" if lineage else "research_policy_denied")


def _material_status(codes: tuple[str, ...], mode: VisibilityMode) -> VisibilityStatus:
    if not codes:
        return "allowed"
    if mode == "audit" and set(codes) <= _INCOMPLETE_CODES:
        return "unknown"
    return "restricted"


def _dimension_status(
    decisions: tuple[MaterialVisibilityDecision, ...],
    *,
    denied_codes: set[str],
) -> VisibilityStatus:
    if any(denied_codes & set(item.safe_codes) for item in decisions):
        return "restricted"
    if any(code in _INCOMPLETE_CODES for item in decisions for code in item.safe_codes):
        return "unknown"
    return "allowed"


def _overall_status(statuses: tuple[VisibilityStatus, ...]) -> VisibilityStatus:
    if all(status == "allowed" for status in statuses):
        return "allowed"
    if any(status == "restricted" for status in statuses):
        return "restricted"
    return "unknown"


def _digest(value: object) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AcceptanceFailure(f"{label} is invalid")
    return value


def _list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise AcceptanceFailure(f"{label} is invalid")
    return value


def _fields_subset(
    value: Mapping[str, object], expected: set[str] | frozenset[str], label: str
) -> None:
    if set(value) - set(expected):
        raise AcceptanceFailure(f"{label} fields are invalid")


def _optional_token(value: object, label: str, missing: list[str]) -> str:
    if value is None:
        missing.append(label)
        return ""
    return _token(value, label)


def _token(value: object, label: str) -> str:
    if not isinstance(value, str) or _SAFE_TOKEN.fullmatch(value) is None:
        raise AcceptanceFailure(f"{label} is invalid")
    return value


def _optional_tokens(value: object, label: str, missing: list[str]) -> tuple[str, ...]:
    if value is None:
        missing.append(label)
        return ()
    return _tokens(value, label)


def _tokens(value: object, label: str, *, empty: bool = False) -> tuple[str, ...]:
    values = _list(value, label)
    if not values and not empty:
        raise AcceptanceFailure(f"{label} is invalid")
    if any(not isinstance(item, str) or _SAFE_TOKEN.fullmatch(item) is None for item in values):
        raise AcceptanceFailure(f"{label} is invalid")
    canonical = tuple(sorted(values))
    if len(canonical) != len(set(canonical)):
        raise AcceptanceFailure(f"{label} is not canonical")
    return canonical


def _optional_label(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 256:
        raise AcceptanceFailure(f"{label} is invalid")
    return value
