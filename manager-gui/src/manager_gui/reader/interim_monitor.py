"""Stdlib-only, fail-closed seam for the V1.2 interim forward monitor.

The monitor is an operational visibility contract, not a research-result API.  This
module validates one immutable public descriptor and a separately published,
owner-authorized exception relation.  It intentionally has no Runtime, holdout
payload, artifact, or result-reading API.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Literal, Protocol, cast

INTERIM_MONITOR_SCHEMA: Final = "apex-research.interim-forward-monitor.v1"
INTERIM_MONITOR_ID: Final = "7ae019274b9d7da0480700aa6ad96da2557fe22681d3ef448fccd1c78e53e404"
INTERIM_MONITOR_MODE: Final = "descriptive_only_non_primary"
INTERIM_MONITOR_STATUS: Final = "registered_not_started"

HOLDOUT_LOCK_SCHEMA: Final = "apex-research.prospective-holdout-lock.v1"
HOLDOUT_ACCESS_PROOF_SCHEMA: Final = "apex-research.prospective-holdout-access-proof.v1"
PRIMARY_HOLDOUT_ISSUE: Final = "#654"
PRIMARY_HOLDOUT_LOCK_ID: Final = "970dedc408332d36eb6d105a993fab3ff07a7f5bccfafd89a554eec1e76435a7"
PRIMARY_HOLDOUT_ACCESS_PROOF_ID: Final = (
    "8add6937e4323ea869173665c1303b9fc7027fb380c9d7aa06c6bc50c3c4dd4a"
)
PRIMARY_HOLDOUT_CUTOFF: Final = date(2026, 12, 31)

INTERIM_EXCEPTION_SCHEMA: Final = "apex-research.interim-monitor-exception.v1"
INTERIM_EXCEPTION_RELATION: Final = "authorizes-pre-gate-strategy-checkpoint"
PUBLICATION_SCHEMA: Final = "quant-research.publication.v1"

MATRIX_ID: Final = "7523f0c34e7d90b6e603f63cc53884284d05664351b68d0a59805e9cf8d95bb5"
T2_ID: Final = "0cc1f61f6528720a0145206419362872d4ff8fba9e676ef8f3ac358e4450cf35"
REPORT_SOURCE_ID: Final = "79d7bf225182dcaa7999e38613f0da690291c21b8ed7396d291ac389d5a9f99f"
QUARANTINE_ID: Final = "33a9500fad482531b6a4747c67c62dd16132f579782d28234bf8815ee5dfedfc"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object with string keys")
    return cast(Mapping[str, object], value)


def _sequence(value: object, name: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be an array")
    return value


def _strict_fields(value: Mapping[str, object], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{name} fields must be {sorted(expected)}")


def _canonical_sha256(value: Mapping[str, object]) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("identity payload must be canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _sha256(value: object, name: str) -> str:
    text = _text(value, name)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{name} must be a lowercase SHA-256 identity")
    return text


def _fixed(value: object, expected: object, name: str) -> None:
    if value != expected or type(value) is not type(expected):
        raise ValueError(f"{name} is not the immutable registered value")


@dataclass(frozen=True, slots=True)
class PublishedRecordRef:
    """An immutable reference to a published public record, never its payload."""

    record_id: str
    record_type: str

    def __post_init__(self) -> None:
        _text(self.record_id, "record_id")
        _text(self.record_type, "record_type")

    def to_wire(self) -> dict[str, str]:
        return {"record_id": self.record_id, "record_type": self.record_type}

    @classmethod
    def from_wire(cls, value: object) -> PublishedRecordRef:
        item = _mapping(value, "record_ref")
        _strict_fields(item, {"record_id", "record_type"}, "record_ref")
        return cls(_text(item["record_id"], "record_id"), _text(item["record_type"], "record_type"))


# The explicit alias is convenient for callers that describe the seam as a public reference.
PublicRecordRef = PublishedRecordRef


@dataclass(frozen=True, slots=True)
class PrimaryHoldout:
    issue: str = PRIMARY_HOLDOUT_ISSUE
    lock_id: str = PRIMARY_HOLDOUT_LOCK_ID
    access_proof_id: str = PRIMARY_HOLDOUT_ACCESS_PROOF_ID
    window: str = "first A-share trading day of October 2026 through 2026-12-31 inclusive"
    minimum_closed_trades: int = 30
    no_extension: bool = True
    evaluation_before_data_complete: bool = False

    def __post_init__(self) -> None:
        _fixed(self.issue, PRIMARY_HOLDOUT_ISSUE, "primary_holdout.issue")
        _fixed(self.lock_id, PRIMARY_HOLDOUT_LOCK_ID, "primary_holdout.lock_id")
        _fixed(
            self.access_proof_id,
            PRIMARY_HOLDOUT_ACCESS_PROOF_ID,
            "primary_holdout.access_proof_id",
        )
        _fixed(
            self.window,
            "first A-share trading day of October 2026 through 2026-12-31 inclusive",
            "primary_holdout.window",
        )
        _fixed(self.minimum_closed_trades, 30, "primary_holdout.minimum_closed_trades")
        _fixed(self.no_extension, True, "primary_holdout.no_extension")
        _fixed(
            self.evaluation_before_data_complete,
            False,
            "primary_holdout.evaluation_before_data_complete",
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "issue": self.issue,
            "lock_id": self.lock_id,
            "access_proof_id": self.access_proof_id,
            "window": self.window,
            "minimum_closed_trades": self.minimum_closed_trades,
            "no_extension": self.no_extension,
            "evaluation_before_data_complete": self.evaluation_before_data_complete,
        }

    @classmethod
    def from_wire(cls, value: object) -> PrimaryHoldout:
        item = _mapping(value, "primary_holdout")
        _strict_fields(
            item,
            {
                "issue",
                "lock_id",
                "access_proof_id",
                "window",
                "minimum_closed_trades",
                "no_extension",
                "evaluation_before_data_complete",
            },
            "primary_holdout",
        )
        return cls(
            _text(item["issue"], "issue"),
            _text(item["lock_id"], "lock_id"),
            _text(item["access_proof_id"], "access_proof_id"),
            _text(item["window"], "window"),
            _int(item["minimum_closed_trades"], "minimum_closed_trades"),
            _bool(item["no_extension"], "no_extension"),
            _bool(item["evaluation_before_data_complete"], "evaluation_before_data_complete"),
        )


@dataclass(frozen=True, slots=True)
class MonitorCadence:
    health_check: str = "daily_allowed"
    descriptive_checkpoint: str = "weekly_not_started"

    def __post_init__(self) -> None:
        _fixed(self.health_check, "daily_allowed", "cadence.health_check")
        _fixed(self.descriptive_checkpoint, "weekly_not_started", "cadence.descriptive_checkpoint")

    def to_wire(self) -> dict[str, str]:
        return {
            "health_check": self.health_check,
            "descriptive_checkpoint": self.descriptive_checkpoint,
        }

    @classmethod
    def from_wire(cls, value: object) -> MonitorCadence:
        item = _mapping(value, "cadence")
        _strict_fields(item, {"health_check", "descriptive_checkpoint"}, "cadence")
        return cls(
            _text(item["health_check"], "health_check"),
            _text(item["descriptive_checkpoint"], "descriptive_checkpoint"),
        )


@dataclass(frozen=True, slots=True)
class FrozenCurrentEvidence:
    matrix: str = MATRIX_ID
    t2: str = T2_ID
    report_source: str = REPORT_SOURCE_ID
    quarantine: str = QUARANTINE_ID

    def __post_init__(self) -> None:
        _fixed(self.matrix, MATRIX_ID, "frozen_current_evidence.matrix")
        _fixed(self.t2, T2_ID, "frozen_current_evidence.t2")
        _fixed(self.report_source, REPORT_SOURCE_ID, "frozen_current_evidence.report_source")
        _fixed(self.quarantine, QUARANTINE_ID, "frozen_current_evidence.quarantine")

    def to_wire(self) -> dict[str, str]:
        return {
            "matrix": self.matrix,
            "t2": self.t2,
            "report_source": self.report_source,
            "quarantine": self.quarantine,
        }

    @classmethod
    def from_wire(cls, value: object) -> FrozenCurrentEvidence:
        item = _mapping(value, "frozen_current_evidence")
        _strict_fields(
            item, {"matrix", "t2", "report_source", "quarantine"}, "frozen_current_evidence"
        )
        return cls(
            _text(item["matrix"], "matrix"),
            _text(item["t2"], "t2"),
            _text(item["report_source"], "report_source"),
            _text(item["quarantine"], "quarantine"),
        )


@dataclass(frozen=True, slots=True)
class MonitorRules:
    parameter_changes: str = "prohibited"
    package_replacement: str = "prohibited"
    unregistered_selection: str = "prohibited"
    optional_stopping: str = "prohibited"
    primary_matrix_or_t2_input: str = "prohibited"
    profitability_or_production_claim: str = "prohibited"
    pre_gate_strategy_level_access: str = (
        "prohibited_without_separate_owner_authorized_exception_record"
    )
    pre_gate_allowed_access: tuple[str, ...] = ("market_data_health_only",)
    holdout_substitution: str = "prohibited"
    fallback_or_zero_fill: str = "prohibited"

    def __post_init__(self) -> None:
        _fixed(self.parameter_changes, "prohibited", "rules.parameter_changes")
        _fixed(self.package_replacement, "prohibited", "rules.package_replacement")
        _fixed(self.unregistered_selection, "prohibited", "rules.unregistered_selection")
        _fixed(self.optional_stopping, "prohibited", "rules.optional_stopping")
        _fixed(self.primary_matrix_or_t2_input, "prohibited", "rules.primary_matrix_or_t2_input")
        _fixed(
            self.profitability_or_production_claim,
            "prohibited",
            "rules.profitability_or_production_claim",
        )
        _fixed(
            self.pre_gate_strategy_level_access,
            "prohibited_without_separate_owner_authorized_exception_record",
            "rules.pre_gate_strategy_level_access",
        )
        _fixed(
            self.pre_gate_allowed_access,
            ("market_data_health_only",),
            "rules.pre_gate_allowed_access",
        )
        _fixed(self.holdout_substitution, "prohibited", "rules.holdout_substitution")
        _fixed(self.fallback_or_zero_fill, "prohibited", "rules.fallback_or_zero_fill")

    def to_wire(self) -> dict[str, object]:
        return {
            "parameter_changes": self.parameter_changes,
            "package_replacement": self.package_replacement,
            "unregistered_selection": self.unregistered_selection,
            "optional_stopping": self.optional_stopping,
            "primary_matrix_or_t2_input": self.primary_matrix_or_t2_input,
            "profitability_or_production_claim": self.profitability_or_production_claim,
            "pre_gate_strategy_level_access": self.pre_gate_strategy_level_access,
            "pre_gate_allowed_access": list(self.pre_gate_allowed_access),
            "holdout_substitution": self.holdout_substitution,
            "fallback_or_zero_fill": self.fallback_or_zero_fill,
        }

    @classmethod
    def from_wire(cls, value: object) -> MonitorRules:
        item = _mapping(value, "rules")
        _strict_fields(
            item,
            {
                "parameter_changes",
                "package_replacement",
                "unregistered_selection",
                "optional_stopping",
                "primary_matrix_or_t2_input",
                "profitability_or_production_claim",
                "pre_gate_strategy_level_access",
                "pre_gate_allowed_access",
                "holdout_substitution",
                "fallback_or_zero_fill",
            },
            "rules",
        )
        return cls(
            _text(item["parameter_changes"], "parameter_changes"),
            _text(item["package_replacement"], "package_replacement"),
            _text(item["unregistered_selection"], "unregistered_selection"),
            _text(item["optional_stopping"], "optional_stopping"),
            _text(item["primary_matrix_or_t2_input"], "primary_matrix_or_t2_input"),
            _text(item["profitability_or_production_claim"], "profitability_or_production_claim"),
            _text(item["pre_gate_strategy_level_access"], "pre_gate_strategy_level_access"),
            tuple(
                _text(entry, "pre_gate_allowed_access[]")
                for entry in _sequence(item["pre_gate_allowed_access"], "pre_gate_allowed_access")
            ),
            _text(item["holdout_substitution"], "holdout_substitution"),
            _text(item["fallback_or_zero_fill"], "fallback_or_zero_fill"),
        )


@dataclass(frozen=True, slots=True)
class RequiredExceptionRelation:
    before_strategy_level_interim_access: bool = True
    must_be_public_immutable_record: bool = True
    must_explicitly_reference: str = PRIMARY_HOLDOUT_ISSUE
    must_not_be_inferred_from_renamed_protocol: bool = True

    def __post_init__(self) -> None:
        _fixed(
            self.before_strategy_level_interim_access,
            True,
            "required_exception_relation.before_strategy_level_interim_access",
        )
        _fixed(
            self.must_be_public_immutable_record,
            True,
            "required_exception_relation.must_be_public_immutable_record",
        )
        _fixed(
            self.must_explicitly_reference,
            PRIMARY_HOLDOUT_ISSUE,
            "required_exception_relation.must_explicitly_reference",
        )
        _fixed(
            self.must_not_be_inferred_from_renamed_protocol,
            True,
            "required_exception_relation.must_not_be_inferred_from_renamed_protocol",
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "before_strategy_level_interim_access": self.before_strategy_level_interim_access,
            "must_be_public_immutable_record": self.must_be_public_immutable_record,
            "must_explicitly_reference": self.must_explicitly_reference,
            "must_not_be_inferred_from_renamed_protocol": (
                self.must_not_be_inferred_from_renamed_protocol
            ),
        }

    @classmethod
    def from_wire(cls, value: object) -> RequiredExceptionRelation:
        item = _mapping(value, "required_exception_relation")
        _strict_fields(
            item,
            {
                "before_strategy_level_interim_access",
                "must_be_public_immutable_record",
                "must_explicitly_reference",
                "must_not_be_inferred_from_renamed_protocol",
            },
            "required_exception_relation",
        )
        return cls(
            _bool(
                item["before_strategy_level_interim_access"], "before_strategy_level_interim_access"
            ),
            _bool(item["must_be_public_immutable_record"], "must_be_public_immutable_record"),
            _text(item["must_explicitly_reference"], "must_explicitly_reference"),
            _bool(
                item["must_not_be_inferred_from_renamed_protocol"],
                "must_not_be_inferred_from_renamed_protocol",
            ),
        )


@dataclass(frozen=True, slots=True)
class InterimMonitorDescriptor:
    """The exact immutable descriptor registered by #685."""

    schema_id: str = INTERIM_MONITOR_SCHEMA
    status: str = INTERIM_MONITOR_STATUS
    mode: str = INTERIM_MONITOR_MODE
    purpose: str = "early operational visibility without replacing the primary forward holdout"
    primary_holdout: PrimaryHoldout = PrimaryHoldout()
    cadence: MonitorCadence = MonitorCadence()
    frozen_current_evidence: FrozenCurrentEvidence = FrozenCurrentEvidence()
    rules: MonitorRules = MonitorRules()
    required_exception_relation: RequiredExceptionRelation = RequiredExceptionRelation()
    owner_scope: str = "QuantResearch V1.2 post-S6 monitoring"
    created_by: str = "#685"

    def __post_init__(self) -> None:
        _fixed(self.schema_id, INTERIM_MONITOR_SCHEMA, "schema")
        _fixed(self.status, INTERIM_MONITOR_STATUS, "status")
        _fixed(self.mode, INTERIM_MONITOR_MODE, "mode")
        _fixed(
            self.purpose,
            "early operational visibility without replacing the primary forward holdout",
            "purpose",
        )
        for name, value, expected_type in (
            ("primary_holdout", self.primary_holdout, PrimaryHoldout),
            ("cadence", self.cadence, MonitorCadence),
            ("frozen_current_evidence", self.frozen_current_evidence, FrozenCurrentEvidence),
            ("rules", self.rules, MonitorRules),
            (
                "required_exception_relation",
                self.required_exception_relation,
                RequiredExceptionRelation,
            ),
        ):
            if not isinstance(value, expected_type):
                raise ValueError(f"{name} must be immutable {expected_type.__name__}")
        _fixed(self.owner_scope, "QuantResearch V1.2 post-S6 monitoring", "owner_scope")
        _fixed(self.created_by, "#685", "created_by")
        if self.identity_sha256 != INTERIM_MONITOR_ID:
            raise ValueError("interim monitor descriptor identity mismatch")

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.identity_payload())

    def identity_payload(self) -> dict[str, object]:
        return self.to_wire()

    def to_wire(self) -> dict[str, object]:
        return {
            "schema": self.schema_id,
            "status": self.status,
            "mode": self.mode,
            "purpose": self.purpose,
            "primary_holdout": self.primary_holdout.to_wire(),
            "cadence": self.cadence.to_wire(),
            "frozen_current_evidence": self.frozen_current_evidence.to_wire(),
            "rules": self.rules.to_wire(),
            "required_exception_relation": self.required_exception_relation.to_wire(),
            "owner_scope": self.owner_scope,
            "created_by": self.created_by,
        }

    @classmethod
    def from_wire(cls, value: object) -> InterimMonitorDescriptor:
        item = _mapping(value, "interim monitor descriptor")
        _strict_fields(
            item,
            {
                "schema",
                "status",
                "mode",
                "purpose",
                "primary_holdout",
                "cadence",
                "frozen_current_evidence",
                "rules",
                "required_exception_relation",
                "owner_scope",
                "created_by",
            },
            "interim monitor descriptor",
        )
        return cls(
            _text(item["schema"], "schema"),
            _text(item["status"], "status"),
            _text(item["mode"], "mode"),
            _text(item["purpose"], "purpose"),
            PrimaryHoldout.from_wire(item["primary_holdout"]),
            MonitorCadence.from_wire(item["cadence"]),
            FrozenCurrentEvidence.from_wire(item["frozen_current_evidence"]),
            MonitorRules.from_wire(item["rules"]),
            RequiredExceptionRelation.from_wire(item["required_exception_relation"]),
            _text(item["owner_scope"], "owner_scope"),
            _text(item["created_by"], "created_by"),
        )

    def ref(self) -> PublishedRecordRef:
        return PublishedRecordRef(INTERIM_MONITOR_ID, INTERIM_MONITOR_SCHEMA)

    def to_publication(self) -> dict[str, object]:
        return _publication(self.ref(), self.to_wire(), ())


class InterimMonitorContractError(ValueError):
    """A public descriptor or authorization relation is structurally invalid."""


class InterimMonitorAccessDenied(InterimMonitorContractError):
    """A requested monitor access is outside the currently authorized boundary."""


class InterimMonitorPrimaryUseDenied(InterimMonitorContractError):
    """An interim output was offered as primary research evidence."""


@dataclass(frozen=True, slots=True)
class ExceptionLineage:
    source_kind: str
    source_id: str
    relation: str

    def __post_init__(self) -> None:
        _text(self.source_kind, "source_kind")
        _text(self.source_id, "source_id")
        _text(self.relation, "relation")

    def to_wire(self) -> dict[str, str]:
        return {
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "relation": self.relation,
        }

    @classmethod
    def from_wire(cls, value: object) -> ExceptionLineage:
        item = _mapping(value, "exception lineage")
        _strict_fields(item, {"source_kind", "source_id", "relation"}, "exception lineage")
        return cls(
            _text(item["source_kind"], "source_kind"),
            _text(item["source_id"], "source_id"),
            _text(item["relation"], "relation"),
        )


@dataclass(frozen=True, slots=True)
class InterimMonitorExceptionRelation:
    """A separate immutable owner authorization bound to exact #654 lineage."""

    relation_id: str
    owner_basis: Literal["owner_direct", "owner_delegated"]
    approver: str
    basis_reference: str
    descriptor: PublishedRecordRef = PublishedRecordRef(INTERIM_MONITOR_ID, INTERIM_MONITOR_SCHEMA)
    holdout_issue: str = PRIMARY_HOLDOUT_ISSUE
    holdout_lock: PublishedRecordRef = PublishedRecordRef(
        PRIMARY_HOLDOUT_LOCK_ID, HOLDOUT_LOCK_SCHEMA
    )
    access_proof: PublishedRecordRef = PublishedRecordRef(
        PRIMARY_HOLDOUT_ACCESS_PROOF_ID, HOLDOUT_ACCESS_PROOF_SCHEMA
    )
    schema_id: str = INTERIM_EXCEPTION_SCHEMA
    schema_version: int = 1
    relation: str = INTERIM_EXCEPTION_RELATION
    status: str = "owner_authorized"
    scope: str = "strategy_checkpoint"

    def __post_init__(self) -> None:
        _sha256(self.relation_id, "relation_id")
        _fixed(self.schema_id, INTERIM_EXCEPTION_SCHEMA, "schema")
        _fixed(self.schema_version, 1, "schema_version")
        _fixed(self.relation, INTERIM_EXCEPTION_RELATION, "relation")
        _fixed(self.status, "owner_authorized", "status")
        _fixed(self.scope, "strategy_checkpoint", "scope")
        if self.owner_basis not in {"owner_direct", "owner_delegated"}:
            raise ValueError("owner_basis must be owner_direct or owner_delegated")
        _text(self.approver, "approver")
        _text(self.basis_reference, "basis_reference")
        _fixed(self.holdout_issue, PRIMARY_HOLDOUT_ISSUE, "holdout_issue")
        if self.descriptor != PublishedRecordRef(INTERIM_MONITOR_ID, INTERIM_MONITOR_SCHEMA):
            raise ValueError("exception must reference the immutable interim descriptor")
        if self.holdout_lock != PublishedRecordRef(PRIMARY_HOLDOUT_LOCK_ID, HOLDOUT_LOCK_SCHEMA):
            raise ValueError("exception must reference the #654 holdout lock")
        if self.access_proof != PublishedRecordRef(
            PRIMARY_HOLDOUT_ACCESS_PROOF_ID, HOLDOUT_ACCESS_PROOF_SCHEMA
        ):
            raise ValueError("exception must reference the #654 no-access proof")
        if self.relation_id != _canonical_sha256(self.identity_payload()):
            raise ValueError("interim monitor exception identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        owner_basis: Literal["owner_direct", "owner_delegated"],
        approver: str,
        basis_reference: str,
        descriptor: PublishedRecordRef | None = None,
        holdout_lock: PublishedRecordRef | None = None,
        access_proof: PublishedRecordRef | None = None,
    ) -> InterimMonitorExceptionRelation:
        relation_values = {
            "schema": INTERIM_EXCEPTION_SCHEMA,
            "schema_version": 1,
            "relation": INTERIM_EXCEPTION_RELATION,
            "status": "owner_authorized",
            "scope": "strategy_checkpoint",
            "owner_basis": owner_basis,
            "approver": approver,
            "basis_reference": basis_reference,
            "descriptor": (
                descriptor or PublishedRecordRef(INTERIM_MONITOR_ID, INTERIM_MONITOR_SCHEMA)
            ).to_wire(),
            "holdout_issue": PRIMARY_HOLDOUT_ISSUE,
            "holdout_lock": (
                holdout_lock or PublishedRecordRef(PRIMARY_HOLDOUT_LOCK_ID, HOLDOUT_LOCK_SCHEMA)
            ).to_wire(),
            "access_proof": (
                access_proof
                or PublishedRecordRef(PRIMARY_HOLDOUT_ACCESS_PROOF_ID, HOLDOUT_ACCESS_PROOF_SCHEMA)
            ).to_wire(),
        }
        return cls(
            _canonical_sha256(relation_values),
            owner_basis,
            approver,
            basis_reference,
            descriptor or PublishedRecordRef(INTERIM_MONITOR_ID, INTERIM_MONITOR_SCHEMA),
            PRIMARY_HOLDOUT_ISSUE,
            holdout_lock or PublishedRecordRef(PRIMARY_HOLDOUT_LOCK_ID, HOLDOUT_LOCK_SCHEMA),
            access_proof
            or PublishedRecordRef(PRIMARY_HOLDOUT_ACCESS_PROOF_ID, HOLDOUT_ACCESS_PROOF_SCHEMA),
        )

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema_id,
            "schema_version": self.schema_version,
            "relation": self.relation,
            "status": self.status,
            "scope": self.scope,
            "owner_basis": self.owner_basis,
            "approver": self.approver,
            "basis_reference": self.basis_reference,
            "descriptor": self.descriptor.to_wire(),
            "holdout_issue": self.holdout_issue,
            "holdout_lock": self.holdout_lock.to_wire(),
            "access_proof": self.access_proof.to_wire(),
        }

    def to_wire(self) -> dict[str, object]:
        return {"relation_id": self.relation_id, **self.identity_payload()}

    @classmethod
    def from_wire(cls, value: object) -> InterimMonitorExceptionRelation:
        item = _mapping(value, "interim monitor exception")
        _strict_fields(
            item,
            {
                "schema",
                "schema_version",
                "relation_id",
                "relation",
                "status",
                "scope",
                "owner_basis",
                "approver",
                "basis_reference",
                "descriptor",
                "holdout_issue",
                "holdout_lock",
                "access_proof",
            },
            "interim monitor exception",
        )
        owner_basis = _text(item["owner_basis"], "owner_basis")
        if owner_basis not in {"owner_direct", "owner_delegated"}:
            raise ValueError("owner_basis must be owner_direct or owner_delegated")
        return cls(
            _sha256(item["relation_id"], "relation_id"),
            cast(Literal["owner_direct", "owner_delegated"], owner_basis),
            _text(item["approver"], "approver"),
            _text(item["basis_reference"], "basis_reference"),
            PublishedRecordRef.from_wire(item["descriptor"]),
            _text(item["holdout_issue"], "holdout_issue"),
            PublishedRecordRef.from_wire(item["holdout_lock"]),
            PublishedRecordRef.from_wire(item["access_proof"]),
            _text(item["schema"], "schema"),
            _int(item["schema_version"], "schema_version"),
            _text(item["relation"], "relation"),
            _text(item["status"], "status"),
            _text(item["scope"], "scope"),
        )

    def ref(self) -> PublishedRecordRef:
        return PublishedRecordRef(self.relation_id, INTERIM_EXCEPTION_SCHEMA)

    def lineage(self) -> tuple[ExceptionLineage, ...]:
        return (
            ExceptionLineage(
                "issue", PRIMARY_HOLDOUT_ISSUE, "exception-to-primary-holdout-time-gate"
            ),
            ExceptionLineage(
                INTERIM_MONITOR_SCHEMA, INTERIM_MONITOR_ID, "exception-for-interim-descriptor"
            ),
            ExceptionLineage(
                HOLDOUT_LOCK_SCHEMA, PRIMARY_HOLDOUT_LOCK_ID, "binds-primary-holdout-lock"
            ),
            ExceptionLineage(
                HOLDOUT_ACCESS_PROOF_SCHEMA,
                PRIMARY_HOLDOUT_ACCESS_PROOF_ID,
                "binds-primary-holdout-access-proof",
            ),
        )

    def to_publication(self) -> dict[str, object]:
        return _publication(
            self.ref(), self.to_wire(), tuple(item.to_wire() for item in self.lineage())
        )


class PublicRecordReader(Protocol):
    """The minimal public readback seam; no Runtime or holdout payload methods exist here."""

    def get_record(self, record_id: str) -> object: ...


def _publication(
    reference: PublishedRecordRef,
    payload: Mapping[str, object],
    lineage: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "schema": PUBLICATION_SCHEMA,
        "record_id": reference.record_id,
        "record_type": reference.record_type,
        "payload": dict(payload),
        "artifacts": [],
        "lineage": [dict(item) for item in lineage],
    }


def _publication_payload(
    value: object, name: str
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    publication = _mapping(value, name)
    required = {"schema", "record_id", "record_type", "payload", "artifacts", "lineage"}
    allowed = required | {"created_at"}
    if set(publication) - allowed or not required <= set(publication):
        raise ValueError(f"{name} requires a strict public publication envelope")
    if publication["schema"] != PUBLICATION_SCHEMA:
        raise ValueError(f"{name} publication schema is invalid")
    if "created_at" in publication:
        created_at = _text(publication["created_at"], f"{name}.created_at")
        try:
            parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{name}.created_at is invalid") from exc
        if parsed.tzinfo is None:
            raise ValueError(f"{name}.created_at must include a timezone")
    if publication["artifacts"] != []:
        raise ValueError(f"{name} publication cannot carry artifacts")
    payload = _mapping(publication["payload"], f"{name}.payload")
    return payload, publication


def validate_descriptor_publication(value: object) -> InterimMonitorDescriptor:
    """Validate an immutable descriptor publication and its content hash."""
    payload, publication = _publication_payload(value, "interim monitor descriptor")
    if publication["record_id"] != INTERIM_MONITOR_ID:
        raise ValueError("interim monitor descriptor identity mismatch")
    if publication["record_type"] != INTERIM_MONITOR_SCHEMA:
        raise ValueError("interim monitor descriptor type mismatch")
    if publication["lineage"] != []:
        raise ValueError("interim monitor descriptor publication is not immutable")
    if _canonical_sha256(payload) != INTERIM_MONITOR_ID:
        raise ValueError("interim monitor descriptor payload hash mismatch")
    return InterimMonitorDescriptor.from_wire(payload)


def validate_exception_publication(value: object) -> InterimMonitorExceptionRelation:
    """Validate a separately published exception and its exact owner lineage."""
    payload, publication = _publication_payload(value, "interim monitor exception")
    relation = InterimMonitorExceptionRelation.from_wire(payload)
    if publication["record_id"] != relation.relation_id:
        raise ValueError("interim monitor exception identity mismatch")
    if publication["record_type"] != INTERIM_EXCEPTION_SCHEMA:
        raise ValueError("interim monitor exception type mismatch")
    if publication["lineage"] != [item.to_wire() for item in relation.lineage()]:
        raise ValueError("interim monitor exception lineage is incomplete")
    return relation


def _missing_record(exc: BaseException) -> bool:
    return isinstance(exc, KeyError) or getattr(exc, "code", None) == "record_not_found"


def read_interim_monitor_descriptor(reader: PublicRecordReader) -> InterimMonitorDescriptor:
    """Read the exact descriptor identity through the public record seam.

    There is deliberately no list/latest fallback: an unavailable exact identity is
    unavailable, rather than permission to select another descriptor.
    """
    try:
        value = reader.get_record(INTERIM_MONITOR_ID)
    except Exception as exc:
        if _missing_record(exc):
            raise InterimMonitorContractError(
                "interim monitor descriptor readback is unavailable"
            ) from exc
        raise
    if value is None:
        raise InterimMonitorContractError("interim monitor descriptor readback is unavailable")
    return validate_descriptor_publication(value)


def read_interim_monitor_exception(
    reader: PublicRecordReader, relation_id: str
) -> InterimMonitorExceptionRelation:
    """Read one exact exception identity without reading referenced record payloads."""
    _sha256(relation_id, "relation_id")
    try:
        value = reader.get_record(relation_id)
    except Exception as exc:
        if _missing_record(exc):
            raise InterimMonitorContractError(
                "interim monitor exception readback is unavailable"
            ) from exc
        raise
    if value is None:
        raise InterimMonitorContractError("interim monitor exception readback is unavailable")
    relation = validate_exception_publication(value)
    if relation.relation_id != relation_id:
        raise InterimMonitorContractError("interim monitor exception readback identity mismatch")
    return relation


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise InterimMonitorAccessDenied("monitor access date is invalid") from exc
    raise InterimMonitorAccessDenied("monitor access date is invalid")


class InterimMonitorGuard:
    """Authorize only health checks, then an exact post-gate exception publication."""

    def __init__(self, descriptor: InterimMonitorDescriptor | None = None) -> None:
        if descriptor is None:
            descriptor = InterimMonitorDescriptor()
        if not isinstance(descriptor, InterimMonitorDescriptor):
            raise TypeError("descriptor must be an InterimMonitorDescriptor")
        self.descriptor = InterimMonitorDescriptor.from_wire(descriptor.to_wire())

    def authorize(
        self,
        access: Literal["health_only", "strategy_checkpoint"],
        *,
        as_of: date | datetime | str,
        exception: object | None = None,
        data_complete: bool = False,
    ) -> None:
        """Raise unless the request stays inside the immutable time-gated boundary."""
        if not isinstance(access, str) or access not in {"health_only", "strategy_checkpoint"}:
            raise InterimMonitorAccessDenied("unknown interim monitor access kind")
        access_date = _as_date(as_of)
        if access == "health_only":
            return
        if access_date <= PRIMARY_HOLDOUT_CUTOFF or data_complete is not True:
            raise InterimMonitorAccessDenied(
                "strategy_checkpoint is denied before the complete #654 date gate"
            )
        if not isinstance(exception, Mapping):
            raise InterimMonitorAccessDenied(
                "strategy_checkpoint requires a separately published exception"
            )
        try:
            relation = validate_exception_publication(exception)
        except (ValueError, TypeError, InterimMonitorContractError) as exc:
            raise InterimMonitorAccessDenied("invalid published interim monitor exception") from exc
        if relation.descriptor != self.descriptor.ref():
            raise InterimMonitorAccessDenied("exception is not bound to this monitor descriptor")

    def assert_non_primary_use(self, destination: str) -> None:
        """Reject every route that could turn interim output into primary evidence."""
        if not isinstance(destination, str):
            raise InterimMonitorPrimaryUseDenied("interim monitor destination is invalid")
        if destination in {
            "primary_matrix",
            "t2",
            "conclusion",
            "holdout",
            "formal_result",
        }:
            raise InterimMonitorPrimaryUseDenied(
                "interim monitor outputs cannot feed the primary matrix, T2 or conclusion"
            )


def authorize_interim_access(
    access: Literal["health_only", "strategy_checkpoint"],
    *,
    as_of: date | datetime | str,
    exception: object | None = None,
    descriptor: InterimMonitorDescriptor | None = None,
    data_complete: bool = False,
) -> None:
    """Convenience function for one fail-closed authorization check."""
    InterimMonitorGuard(descriptor).authorize(
        access,
        as_of=as_of,
        exception=exception,
        data_complete=data_complete,
    )


__all__ = [
    "HOLDOUT_ACCESS_PROOF_SCHEMA",
    "HOLDOUT_LOCK_SCHEMA",
    "INTERIM_EXCEPTION_RELATION",
    "INTERIM_EXCEPTION_SCHEMA",
    "INTERIM_MONITOR_ID",
    "INTERIM_MONITOR_MODE",
    "INTERIM_MONITOR_SCHEMA",
    "INTERIM_MONITOR_STATUS",
    "MATRIX_ID",
    "PRIMARY_HOLDOUT_ACCESS_PROOF_ID",
    "PRIMARY_HOLDOUT_CUTOFF",
    "PRIMARY_HOLDOUT_ISSUE",
    "PRIMARY_HOLDOUT_LOCK_ID",
    "PUBLICATION_SCHEMA",
    "QUARANTINE_ID",
    "REPORT_SOURCE_ID",
    "T2_ID",
    "ExceptionLineage",
    "FrozenCurrentEvidence",
    "InterimMonitorAccessDenied",
    "InterimMonitorContractError",
    "InterimMonitorDescriptor",
    "InterimMonitorExceptionRelation",
    "InterimMonitorGuard",
    "InterimMonitorPrimaryUseDenied",
    "MonitorCadence",
    "MonitorRules",
    "PrimaryHoldout",
    "PublicRecordReader",
    "PublicRecordRef",
    "PublishedRecordRef",
    "RequiredExceptionRelation",
    "authorize_interim_access",
    "read_interim_monitor_descriptor",
    "read_interim_monitor_exception",
    "validate_descriptor_publication",
    "validate_exception_publication",
]
