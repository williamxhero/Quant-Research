"""Resumable immutable evidence ledger for the 32-SPEC release train."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from .core import AcceptanceFailure

_REF = re.compile(r"sha256:[0-9a-f]{64}")
_SPEC = re.compile(r"SPEC-[0-9]{3}[A-Z]?")
_ENVIRONMENT_STATUSES = {
    "passed",
    "failed",
    "skipped",
    "unavailable",
    "timed-out",
    "indeterminate",
}
_FINAL_ENVIRONMENT_OWNERS = (
    "apex-research",
    "quant-runtime",
    "strategy-reporting",
)


@dataclass(frozen=True, slots=True)
class GateRequest:
    identity: str
    kind: str
    phase: str
    spec: str
    checkpoint: int
    owners: tuple[str, ...]
    evidence_ref: str
    independent: bool


@dataclass(frozen=True, slots=True)
class EnvironmentOutcome:
    gate_identity: str
    status: str
    evidence_ref: str
    independent: bool = True


class ReleaseTrain:
    """Record ordered SPEC evidence and derive checkpoint gates exactly once."""

    def __init__(
        self,
        specs: tuple[str, ...],
        *,
        batch_size: int = 6,
        connected_impacts: Mapping[str, tuple[str, ...]] | None = None,
    ) -> None:
        if (
            len(specs) != 32
            or len(set(specs)) != len(specs)
            or any(_SPEC.fullmatch(spec) is None for spec in specs)
        ):
            raise AcceptanceFailure("release train must contain 32 unique canonical SPECs")
        if not 5 <= batch_size <= 8:
            raise AcceptanceFailure("release train batch size must be between 5 and 8")
        impacts = dict(connected_impacts or {})
        if any(
            spec not in specs or not owners or owners != tuple(sorted(set(owners)))
            for spec, owners in impacts.items()
        ):
            raise AcceptanceFailure("connected impact map is invalid")
        self._specs = specs
        self._batch_size = batch_size
        self._connected_impacts = dict(sorted(impacts.items()))
        self._evidence: dict[str, str] = {}
        self._gates: dict[str, tuple[GateRequest, ...]] = {}
        self._environment: dict[str, EnvironmentOutcome] = {}

    @property
    def next_spec(self) -> str | None:
        index = len(self._evidence)
        return None if index == len(self._specs) else self._specs[index]

    @property
    def complete(self) -> bool:
        return len(self._evidence) == len(self._specs)

    @property
    def environment_outcomes(self) -> tuple[EnvironmentOutcome, ...]:
        return tuple(self._environment[key] for key in sorted(self._environment))

    def record(self, spec: str, evidence_ref: str) -> tuple[GateRequest, ...]:
        _evidence_ref(evidence_ref)
        if spec in self._evidence:
            if self._evidence[spec] != evidence_ref:
                raise AcceptanceFailure(f"immutable SPEC evidence drifted: {spec}")
            return self._gates[spec]
        if spec != self.next_spec:
            raise AcceptanceFailure(
                f"release train is out of order: expected {self.next_spec}, got {spec}"
            )
        checkpoint = len(self._evidence) + 1
        gates = [
            _gate(
                kind="incremental",
                phase="spec",
                spec=spec,
                checkpoint=checkpoint,
                owners=(),
                evidence_ref=evidence_ref,
                independent=False,
            )
        ]
        if checkpoint < len(self._specs) and checkpoint % self._batch_size == 0:
            gates.append(
                _gate(
                    kind="medium-integration",
                    phase="batch",
                    spec=spec,
                    checkpoint=checkpoint,
                    owners=(),
                    evidence_ref=evidence_ref,
                    independent=False,
                )
            )
        impacted = self._connected_impacts.get(spec, ())
        if checkpoint == len(self._specs):
            gates.append(
                _gate(
                    kind="owner-full-regression",
                    phase="release",
                    spec=spec,
                    checkpoint=checkpoint,
                    owners=(),
                    evidence_ref=evidence_ref,
                    independent=False,
                )
            )
            impacted = _FINAL_ENVIRONMENT_OWNERS
        if impacted:
            gates.append(
                _gate(
                    kind="environment-status",
                    phase="release" if checkpoint == len(self._specs) else "spec",
                    spec=spec,
                    checkpoint=checkpoint,
                    owners=impacted,
                    evidence_ref=evidence_ref,
                    independent=True,
                )
            )
        result = tuple(gates)
        self._evidence[spec] = evidence_ref
        self._gates[spec] = result
        return result

    def record_environment(self, gate_identity: str, *, status: str, evidence_ref: str) -> None:
        _evidence_ref(evidence_ref)
        gate = next(
            (
                item
                for gates in self._gates.values()
                for item in gates
                if item.identity == gate_identity and item.kind == "environment-status"
            ),
            None,
        )
        if gate is None or status not in _ENVIRONMENT_STATUSES:
            raise AcceptanceFailure("environment outcome is invalid")
        outcome = EnvironmentOutcome(gate_identity, status, evidence_ref)
        previous = self._environment.get(gate_identity)
        if previous is not None and previous != outcome:
            raise AcceptanceFailure("immutable environment outcome drifted")
        self._environment[gate_identity] = outcome

    def snapshot(self) -> dict[str, object]:
        return {
            "schema": "quant-research.release-train-ledger.v1",
            "specs": list(self._specs),
            "batch_size": self._batch_size,
            "connected_impacts": {
                spec: list(owners) for spec, owners in self._connected_impacts.items()
            },
            "evidence": [
                {"spec": spec, "evidence_ref": self._evidence[spec]}
                for spec in self._specs
                if spec in self._evidence
            ],
            "environment_outcomes": [
                {
                    "gate_identity": outcome.gate_identity,
                    "status": outcome.status,
                    "evidence_ref": outcome.evidence_ref,
                    "independent": True,
                }
                for outcome in self.environment_outcomes
            ],
        }

    @classmethod
    def restore(cls, snapshot: Mapping[str, object]) -> ReleaseTrain:
        expected = {
            "schema",
            "specs",
            "batch_size",
            "connected_impacts",
            "evidence",
            "environment_outcomes",
        }
        if (
            set(snapshot) != expected
            or snapshot.get("schema") != "quant-research.release-train-ledger.v1"
        ):
            raise AcceptanceFailure("release train snapshot is invalid")
        try:
            specs = tuple(snapshot["specs"])  # type: ignore[arg-type]
            impacts = {
                spec: tuple(owners)
                for spec, owners in snapshot["connected_impacts"].items()  # type: ignore[union-attr]
            }
            train = cls(specs, batch_size=snapshot["batch_size"], connected_impacts=impacts)  # type: ignore[arg-type]
            for item in snapshot["evidence"]:  # type: ignore[union-attr]
                train.record(item["spec"], item["evidence_ref"])
            for item in snapshot["environment_outcomes"]:  # type: ignore[union-attr]
                if item.get("independent") is not True:
                    raise AcceptanceFailure("environment outcome lost independence")
                train.record_environment(
                    item["gate_identity"],
                    status=item["status"],
                    evidence_ref=item["evidence_ref"],
                )
        except (KeyError, TypeError, AttributeError) as exc:
            raise AcceptanceFailure("release train snapshot is invalid") from exc
        if train.snapshot() != dict(snapshot):
            raise AcceptanceFailure("release train snapshot is not canonical")
        return train


def _gate(
    *,
    kind: str,
    phase: str,
    spec: str,
    checkpoint: int,
    owners: tuple[str, ...],
    evidence_ref: str,
    independent: bool,
) -> GateRequest:
    material = {
        "kind": kind,
        "phase": phase,
        "spec": spec,
        "checkpoint": checkpoint,
        "owners": list(owners),
        "evidence_ref": evidence_ref,
        "independent": independent,
    }
    identity = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return GateRequest(
        identity,
        kind,
        phase,
        spec,
        checkpoint,
        owners,
        evidence_ref,
        independent,
    )


def _evidence_ref(value: str) -> None:
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        raise AcceptanceFailure("evidence reference must be an immutable sha256")
