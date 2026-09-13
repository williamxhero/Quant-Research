"""Versioned evidence contracts for acceptance batches.

The historical release train is intentionally a separate contract: it has a
fixed 32-SPEC topology.  A research batch can therefore compose the existing
scope selector without appending entries to that ledger or changing its
meaning.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .core import AcceptanceFailure, AcceptancePlan, AcceptanceSelector

BatchStatus = Literal["pass", "fail", "expected-deny", "blocked", "not_run"]
_BATCH_ID = re.compile(r"[A-Z][A-Z0-9-]{0,31}")
_CASE_ID = re.compile(r"A0-[A-Z][0-9]{2}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")

_STATUSES = ("pass", "fail", "expected-deny", "blocked", "not_run")
_REQUIRED_CONFIG_FIELDS = {
    "schema",
    "batch_id",
    "revision",
    "scope_schema",
    "scope_revision",
    "required_cases",
    "scenario_to_direct_tests",
    "fixture_binding",
}


@dataclass(frozen=True, slots=True)
class A0BatchConfig:
    """Strict, machine-readable configuration for one non-legacy batch."""

    batch_id: str
    revision: int
    scope_schema: str
    scope_revision: str
    required_cases: tuple[str, ...]
    scenario_to_direct_tests: tuple[tuple[str, tuple[str, ...]], ...]
    fixture_binding: tuple[tuple[str, str], ...]

    @classmethod
    def parse(cls, value: Mapping[str, object]) -> A0BatchConfig:
        if set(value) != _REQUIRED_CONFIG_FIELDS:
            raise AcceptanceFailure("acceptance batch config fields are invalid")
        if value.get("schema") != "quant-research.acceptance-batch.v1":
            raise AcceptanceFailure("acceptance batch schema is invalid")
        batch_id = value.get("batch_id")
        revision = value.get("revision")
        scope_schema = value.get("scope_schema")
        scope_revision = value.get("scope_revision")
        if (
            not isinstance(batch_id, str)
            or _BATCH_ID.fullmatch(batch_id) is None
            or not isinstance(revision, int)
            or isinstance(revision, bool)
            or revision < 1
            or not isinstance(scope_schema, str)
            or scope_schema != "quant-research.acceptance-scope.v2"
            or not isinstance(scope_revision, str)
            or not scope_revision
        ):
            raise AcceptanceFailure("acceptance batch identity is invalid")

        raw_cases = _list(value.get("required_cases"), "required cases")
        required_cases = _canonical_case_ids(raw_cases, "required cases")
        raw_mapping = _mapping(value.get("scenario_to_direct_tests"), "scenario mapping")
        mapping: list[tuple[str, tuple[str, ...]]] = []
        for case_id, raw_tests in sorted(raw_mapping.items()):
            if _CASE_ID.fullmatch(case_id) is None:
                raise AcceptanceFailure(f"scenario id is invalid: {case_id}")
            mapping.append((case_id, _canonical_paths(raw_tests, f"tests for {case_id}")))
        if tuple(case_id for case_id, _tests in mapping) != required_cases:
            raise AcceptanceFailure("required cases and scenario mapping differ")

        raw_binding = _mapping(value.get("fixture_binding"), "fixture binding")
        if set(raw_binding) != {"fixture_revision", "fixture_digest", "role"}:
            raise AcceptanceFailure("fixture binding fields are invalid")
        fixture_revision = raw_binding.get("fixture_revision")
        fixture_digest = raw_binding.get("fixture_digest")
        role = raw_binding.get("role")
        if (
            not isinstance(fixture_revision, str)
            or not fixture_revision
            or not isinstance(fixture_digest, str)
            or _DIGEST.fullmatch(fixture_digest) is None
            or role != "synthetic-test-only"
        ):
            raise AcceptanceFailure("fixture binding is invalid")
        return cls(
            batch_id=batch_id,
            revision=revision,
            scope_schema=scope_schema,
            scope_revision=scope_revision,
            required_cases=required_cases,
            scenario_to_direct_tests=tuple(mapping),
            fixture_binding=tuple(sorted((key, str(raw_binding[key])) for key in raw_binding)),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": "quant-research.acceptance-batch.v1",
            "batch_id": self.batch_id,
            "revision": self.revision,
            "scope_schema": self.scope_schema,
            "scope_revision": self.scope_revision,
            "required_cases": list(self.required_cases),
            "scenario_to_direct_tests": {
                case_id: list(tests) for case_id, tests in self.scenario_to_direct_tests
            },
            "fixture_binding": dict(self.fixture_binding),
        }


@dataclass(frozen=True, slots=True)
class A0Selection:
    """Existing execution plan plus the bounded A0 case selection."""

    batch_id: str
    batch_revision: int
    scope_revision: str
    fixture_binding: tuple[tuple[str, str], ...]
    plan: AcceptancePlan
    selected_cases: tuple[str, ...]
    direct_tests: tuple[tuple[str, tuple[str, ...]], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": "quant-research.acceptance-selection.v1",
            "batch_id": self.batch_id,
            "batch_revision": self.batch_revision,
            "scope_revision": self.scope_revision,
            "fixture_binding": dict(self.fixture_binding),
            "selected_cases": list(self.selected_cases),
            "direct_tests": {case_id: list(tests) for case_id, tests in self.direct_tests},
            "plan": self.plan.as_dict(),
        }


class A0BatchSelector:
    """Select an A0 slice through the public, legacy-compatible selector."""

    def select(
        self,
        config: Mapping[str, object] | A0BatchConfig,
        scope: Mapping[str, object],
        fixed_base_diff: Mapping[str, object],
        *,
        phase: Literal["spec", "release"],
    ) -> A0Selection:
        parsed = config if isinstance(config, A0BatchConfig) else A0BatchConfig.parse(config)
        if scope.get("schema") != parsed.scope_schema:
            raise AcceptanceFailure("A0 batch scope schema is incompatible")
        # The scope is still strict v2; its own parser rejects any wrapper fields.
        plan = AcceptanceSelector().select(scope, fixed_base_diff, phase=phase)
        raw_mapping = scope.get("source_to_direct_tests")
        if not isinstance(raw_mapping, Mapping):
            raise AcceptanceFailure("A0 scope direct-test mapping is invalid")
        scope_tests = {
            test
            for raw_tests in raw_mapping.values()
            if isinstance(raw_tests, list)
            for test in raw_tests
            if isinstance(test, str)
        }
        batch_tests = {
            test for _case_id, tests in parsed.scenario_to_direct_tests for test in tests
        }
        if not batch_tests <= scope_tests:
            raise AcceptanceFailure("A0 scenario mapping uses tests outside the scope")
        selected_tests = {test for step in plan.steps for test in step.direct_tests}
        if not batch_tests <= selected_tests:
            raise AcceptanceFailure("A0 scenario mapping is outside the selected impact")
        return A0Selection(
            batch_id=parsed.batch_id,
            batch_revision=parsed.revision,
            scope_revision=parsed.scope_revision,
            fixture_binding=parsed.fixture_binding,
            plan=plan,
            selected_cases=parsed.required_cases,
            direct_tests=parsed.scenario_to_direct_tests,
        )


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    case_id: str
    status: BatchStatus
    evidence_ref: str
    plan_identity: str
    batch_id: str
    batch_revision: int
    fixture_digest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "status": self.status,
            "evidence_ref": self.evidence_ref,
            "plan_identity": self.plan_identity,
            "batch_id": self.batch_id,
            "batch_revision": self.batch_revision,
            "fixture_digest": self.fixture_digest,
        }


class A0EvidenceLedger:
    """Immutable evidence records for a batch; never mutates the 32-SPEC ledger."""

    def __init__(self, selection: A0Selection) -> None:
        self._selection = selection
        self._records: dict[str, EvidenceRecord] = {}

    @property
    def selection(self) -> A0Selection:
        return self._selection

    @property
    def records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(
            self._records[key] for key in self._selection.selected_cases if key in self._records
        )

    def record(
        self,
        case_id: str,
        *,
        status: BatchStatus,
        evidence_ref: str,
        plan_identity: str,
        fixture_digest: str,
    ) -> EvidenceRecord:
        if case_id not in self._selection.selected_cases:
            raise AcceptanceFailure(f"A0 case is not selected: {case_id}")
        if status not in _STATUSES:
            raise AcceptanceFailure(f"A0 evidence status is invalid: {status}")
        if not isinstance(evidence_ref, str) or _DIGEST.fullmatch(evidence_ref) is None:
            raise AcceptanceFailure("A0 evidence reference is invalid")
        if not isinstance(plan_identity, str) or plan_identity != self._selection.plan.identity:
            raise AcceptanceFailure("A0 plan identity is invalid")
        binding = dict(self._selection.fixture_binding)
        if fixture_digest != binding["fixture_digest"]:
            raise AcceptanceFailure("A0 fixture digest drifted")
        record = EvidenceRecord(
            case_id=case_id,
            status=status,
            evidence_ref=evidence_ref,
            plan_identity=plan_identity,
            batch_id=self._selection.batch_id,
            batch_revision=self._selection.batch_revision,
            fixture_digest=fixture_digest,
        )
        previous = self._records.get(case_id)
        if previous is not None and previous != record:
            raise AcceptanceFailure(f"immutable A0 evidence drifted: {case_id}")
        self._records[case_id] = record
        return record

    def summary(self) -> dict[str, object]:
        counts = {status: 0 for status in _STATUSES}
        for record in self._records.values():
            counts[record.status] += 1
        missing = [
            case_id for case_id in self._selection.selected_cases if case_id not in self._records
        ]
        return {
            "batch_id": self._selection.batch_id,
            "batch_revision": self._selection.batch_revision,
            "plan_identity": self._selection.plan.identity,
            "fixture_digest": dict(self._selection.fixture_binding)["fixture_digest"],
            "counts": counts,
            "missing_cases": missing,
            "complete": not missing,
            "pass_count": counts["pass"],
            "non_pass_cases": sum(counts[status] for status in _STATUSES if status != "pass"),
        }

    def snapshot(self) -> dict[str, object]:
        return {
            "schema": "quant-research.acceptance-batch-ledger.v1",
            "selection": self._selection.as_dict(),
            "records": [record.as_dict() for record in self.records],
        }

    @classmethod
    def restore(cls, selection: A0Selection, snapshot: Mapping[str, object]) -> A0EvidenceLedger:
        if set(snapshot) != {"schema", "selection", "records"}:
            raise AcceptanceFailure("A0 evidence ledger fields are invalid")
        if snapshot.get("schema") != "quant-research.acceptance-batch-ledger.v1":
            raise AcceptanceFailure("A0 evidence ledger schema is invalid")
        if snapshot.get("selection") != selection.as_dict():
            raise AcceptanceFailure("A0 evidence selection drifted")
        raw_records = _list(snapshot.get("records"), "A0 evidence records")
        ledger = cls(selection)
        for raw in raw_records:
            record = _mapping(raw, "A0 evidence record")
            expected = {
                "case_id",
                "status",
                "evidence_ref",
                "plan_identity",
                "batch_id",
                "batch_revision",
                "fixture_digest",
            }
            if set(record) != expected:
                raise AcceptanceFailure("A0 evidence record fields are invalid")
            if (
                record.get("batch_id") != selection.batch_id
                or record.get("batch_revision") != selection.batch_revision
            ):
                raise AcceptanceFailure("A0 evidence batch binding drifted")
            ledger.record(
                str(record["case_id"]),
                status=record["status"],  # type: ignore[arg-type]
                evidence_ref=str(record["evidence_ref"]),
                plan_identity=str(record["plan_identity"]),
                fixture_digest=str(record["fixture_digest"]),
            )
        if ledger.snapshot() != dict(snapshot):
            raise AcceptanceFailure("A0 evidence ledger is not canonical")
        return ledger


# Discoverable aliases for callers that describe this as a batch evidence ledger.
BatchSelector = A0BatchSelector
BatchEvidenceLedger = A0EvidenceLedger


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise AcceptanceFailure(f"{label} is invalid")
    return value


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise AcceptanceFailure(f"{label} is invalid")
    return value


def _canonical_case_ids(value: list[object], label: str) -> tuple[str, ...]:
    if not value or any(
        not isinstance(item, str) or _CASE_ID.fullmatch(item) is None for item in value
    ):
        raise AcceptanceFailure(f"{label} is invalid")
    if value != sorted(set(value)):
        raise AcceptanceFailure(f"{label} is not canonical")
    return tuple(value)  # type: ignore[return-value]


def _canonical_paths(value: object, label: str) -> tuple[str, ...]:
    raw = _list(value, label)
    if not raw or any(not isinstance(item, str) or not item for item in raw):
        raise AcceptanceFailure(f"{label} is invalid")
    normalized = tuple(item.replace("\\", "/") for item in raw)
    if normalized != tuple(sorted(set(normalized))) or any(
        item.startswith("/") or ".." in item.split("/") or "" in item.split("/")
        for item in normalized
    ):
        raise AcceptanceFailure(f"{label} is not canonical")
    return normalized


def batch_identity(selection: A0Selection) -> str:
    """Return a stable identity for selection metadata, excluding plan artifacts."""
    material = {
        "batch_id": selection.batch_id,
        "batch_revision": selection.batch_revision,
        "scope_revision": selection.scope_revision,
        "fixture_binding": dict(selection.fixture_binding),
        "plan_identity": selection.plan.identity,
        "selected_cases": list(selection.selected_cases),
        "direct_tests": {key: list(value) for key, value in selection.direct_tests},
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
